# Admin SPA refresh — Implementation Plan (v21)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute in order SR1→SR48 unless the parallel-dispatch table below says otherwise.

**Version:** ui 1.1.0 · bot 1.1.2

**Goal:** Bring the Angular admin SPA to the state the Jinja UI reached and past it — a compact/full table model with an SL→TP status bar, a modern-fintech dark palette, a collapsible icon-rail sidebar, four responsive breakpoints down to 390px, one interactive chart carrying everything the Discord PNG draws, and a feature-level parity audit that proves nothing was lost.

**Architecture:** Five phases on one worktree branch, merged to `main` at each phase boundary. Phase 0 is serial and does the wide mechanical edits (palette, two renames, assets) so Phases 1–4 can fan out to parallel subagents without colliding. Every task declares `Owns:` and `Blocked by:`; disjoint `Owns:` sets inside a phase may run concurrently.

**Tech Stack:** Angular 21.2 + `@ngrx/signals` 21.1 + TypeScript · `lightweight-charts` 5.2.1 · Vitest 4 · Flask + Python 3.11 · pytest · mplfinance/matplotlib (PNG side).

**Spec:** `docs/superpowers/specs/2026-08-13-v18-spa-refresh-design.md`. Read the relevant Decision before starting a phase. This plan carries the sequence; the spec carries the reasoning.

---

## Setup, before SR1

Create the worktree with the `superpowers:using-git-worktrees` skill. Branch `worktree-spa-refresh`, off `main`.

```bash
git worktree add .claude/worktrees/spa-refresh -b worktree-spa-refresh main
cd .claude/worktrees/spa-refresh
cd frontend && npm ci && cd ..
```

**Never edit `.claude/worktrees/` from a main-tree session, and never edit the main tree from inside the worktree.** Three worktrees already exist; `.ignore` excludes them from search precisely because sessions have confused them before.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **The bot process is never modified.** The only Python outside `swingbot/admin/` that this plan touches is the chart-geometry extraction (SR32), which is a refactor with byte-identical output, gated as such.
- **Zero runtime CDN calls.** Fonts, icons and charts are self-hosted. A network request to a third-party host is a defect. Icons are hand-authored inline SVG — no icon font, no icon package.
- **No hex literals in `frontend/src` outside `styles/tokens.css`.** Enforced by SR3 and re-checked at each phase gate.
- **No horizontal document scroll at any breakpoint.** Wide content scrolls inside its own `overflow-x: auto` container. This regressed once already (NG54).
- **"Refetch, never patch."** Every event handler in the SPA reissues a query. No client-side reconciliation of server state.
- **Preferences are server-side** (`PreferencesStore` → `/api/v1/preferences`), never `localStorage`. Every read tolerates absence and unknown keys at every level and falls back to the baseline.
- **The API returns token names and numbers, never colours.** No `#rrggbb` crosses the wire into the SPA.
- **Colour rule: one colour, one valence** — `--pos` good · `--neg` bad · `--warn` caution · `--accent` interactive/brand · `--info` neutral information. Everything else greyscale. A sixth hue is a review defect. The one recorded exception is LONG ▲ `--pos` / SHORT ▼ `--neg`.
- **Merge to `main` once per phase, not per task.** Check `git status` on the main tree before merging — other sessions leave it dirty.
- Windows dev machine: `python`, never `python3`.
- `python scripts/testrun.py full` green (`0 failed`) before each commit; `python scripts/testrun.py file tests/admin` while iterating. `cd frontend && npx ng test` for the TS side.
- **`npx ng test`, never bare `npx vitest run`.** The `@angular/build:unit-test` builder is what calls `TestBed.initTestEnvironment()`; running vitest directly makes 18 of 20 spec files fail with "Need to call TestBed.initTestEnvironment() first", which looks like a broken suite and is not. `vitest.config.ts` is only a runner config the builder merges in.
- **`ng test` occasionally dies at exactly 60s** with "Timeout waiting for worker to respond" — a hard-coded vitest constant, load-dependent, documented at the top of `vitest.config.ts`. **A re-run succeeds.** Treat a fresh timeout as "try again", not as a failure.
- Conventional commits, one per task, `git add <explicit paths>` — never `-A`.
- New docs follow `YYYY-MM-DD-vN-<name>.md`; next free number is **v22**.

---

## Parallel dispatch

| Phase | Tasks | Lanes that may run concurrently |
|---|---|---|
| **P0** | SR1–SR6 | **None.** Serial, in order. |
| **P1** | SR7–SR19 | `SR7` ∥ `SR8,SR9,SR10` ∥ `SR12,SR13,SR14,SR15`. Then SR11, then SR16, then SR17+SR18, then SR19. |
| **P2** | SR20–SR31 | `SR20` ∥ `SR23`. Then `SR21,SR22` ∥ `SR24`. Then SR25–SR30 all six concurrently. Then SR31. |
| **P3** | SR32–SR40 | `SR32→SR33` (Python) ∥ `SR34` (the risk gate, TS). Then SR35, which needs both. Then `SR36,SR37,SR38,SR39` concurrently. Then SR40. |
| **P4** | SR41–SR48 | SR41–SR45 all five concurrently. Then SR46, SR47, SR48. |

A dispatching session reads each task's `Owns:` and `Blocked by:` and confirms against this table. Where the two disagree, the task's own lines win — this table is a summary.

---

# Phase 0 — Foundation (SR1–SR6)

Serial. Wide, mechanical, conflict-prone. Nothing fans out until this phase merges.

### Task SR1: Defer NG57 and record the reversals

**Owns:** `docs/superpowers/plans/2026-08-08-v16-angular-migration.md`, `docs/superpowers/specs/2026-08-08-v20-admin-design-system-design.md`, `docs/superpowers/specs/2026-08-08-v14-angular-workspaces-design.md`
**Blocked by:** —

Spec Decision 13. A session resuming NG56 today finds a soak whose end date is approaching and would proceed to delete the templates this plan ports *from*.

- [ ] **Step 1:** In the migration plan's Progress block, replace the `**Next:** NG56` line with:

```markdown
> - **Next:** NG56 — the soak continues, but **NG57 is deferred from a date to
>   an event**: it must not start until plan v21 (`2026-08-13-v21-spa-refresh.md`)
>   completes. That plan ports the density model, the status bar and the plan
>   cell *from* these templates and audits all 19 of them for feature parity.
>   Deleting the reference mid-port is how details get lost. See spec v18
>   Decision 13.
```

- [ ] **Step 2:** Add a `> **Superseded in part by v18**` note directly under the heading of design-system Decision 2 and Decision 3, and under workspaces v14 Decision 5, each naming what changed in one sentence. Do not rewrite the decisions — a superseded decision still records why it was made.
- [ ] **Step 3: Verify** `grep -n "v21-spa-refresh" docs/superpowers/plans/2026-08-08-v16-angular-migration.md` returns the line.
- [ ] **Step 4: Commit** `docs(plans): defer NG57 until the SPA refresh lands`

---

### Task SR2: `tokens.css` — palette, motion, spacing

**Owns:** `frontend/src/styles/tokens.css`, `frontend/src/app/ui/tokens.spec.ts`
**Produces:** every custom property the rest of the plan references. Nothing else may define a colour.
**Blocked by:** SR1

Spec Decisions 2 and 3.

- [ ] **Step 1: Write the failing test** — `frontend/src/app/ui/tokens.spec.ts`. It reads the stylesheet as text rather than mounting a component, because the tokens must exist whether or not anything consumes them yet.

```ts
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(new URL('../../styles/tokens.css', import.meta.url), 'utf8');

const REQUIRED = [
  '--bg', '--surface', '--surface-raised', '--surface-overlay',
  '--border', '--border-strong',
  '--text', '--text-secondary', '--text-muted', '--text-faint',
  '--pos', '--neg', '--warn', '--accent', '--info',
  '--pos-soft', '--neg-soft', '--warn-soft', '--accent-soft', '--info-soft',
  '--dur-instant', '--dur-base', '--dur-slow', '--ease-out', '--ease-spring',
];

describe('design tokens', () => {
  for (const name of REQUIRED) {
    it(`defines ${name}`, () => {
      expect(CSS).toMatch(new RegExp(`^\\s*${name}:`, 'm'));
    });
  }

  it('honours prefers-reduced-motion', () => {
    expect(CSS).toContain('prefers-reduced-motion: reduce');
  });

  it('has dropped --space-28', () => {
    expect(CSS).not.toMatch(/^\s*--space-28:/m);
  });
});
```

- [ ] **Step 2: Run it and watch it fail** — `cd frontend && npx ng test`. Expected: failures on `--surface-overlay`, `--info`, every `-soft`, all three durations, `--ease-spring`, the reduced-motion block; `--space-28` currently passes-as-present so that case fails too.
- [ ] **Step 3: Replace the colour block.**

```css
  --bg: #0a0b10;
  --surface: #10121a;
  --surface-raised: #171a25;
  --surface-overlay: #1e2230;
  --border: #232838;
  --border-strong: #333a4f;

  --text: #e9ebf5;
  --text-secondary: #9ba3bd;
  --text-muted: #6d7590;
  --text-faint: #464d63;

  --pos: #17c98e;
  --neg: #ff5470;
  --warn: #ffb43d;
  --accent: #7b5cfa;
  --info: #46c2ff;

  --pos-soft: rgba(23, 201, 142, 0.12);
  --neg-soft: rgba(255, 84, 112, 0.12);
  --warn-soft: rgba(255, 180, 61, 0.12);
  --accent-soft: rgba(123, 92, 250, 0.12);
  --info-soft: rgba(70, 194, 255, 0.12);
```

- [ ] **Step 4: Replace the quality ramp** — it stops being greyscale (spec Decision 2):

```css
  --quality-5: var(--pos);
  --quality-4: var(--info);
  --quality-3: var(--text-secondary);
  --quality-2: var(--warn);
  --quality-1: var(--neg);
```

Delete `--quality-high` / `--quality-mid` / `--quality-low` and fix their call sites in the same commit (`git grep -n "quality-high\|quality-mid\|quality-low" frontend/src`).

- [ ] **Step 5: Replace the motion block.**

```css
  --dur-instant: 90ms;
  --dur-base: 160ms;
  --dur-slow: 260ms;
  --ease-out: cubic-bezier(0.2, 0.8, 0.3, 1);
  --ease-spring: cubic-bezier(0.34, 1.4, 0.64, 1);

  /* Kept as an alias so existing `transition: var(--transition)` call sites
     keep compiling; new code names the duration it wants. */
  --transition: var(--dur-base) var(--ease-out);
```

- [ ] **Step 6: Drop `--space-28`** and fix its call sites (`git grep -n "space-28" frontend/src`).
- [ ] **Step 7: Add the reduced-motion block**, at file end, outside `:root`:

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --dur-instant: 0ms;
    --dur-base: 0ms;
    --dur-slow: 0ms;
  }
  *, *::before, *::after {
    animation-duration: 0ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0ms !important;
  }
}
```

- [ ] **Step 8: Rewrite the file's header comment.** It currently states the old three-rule colour system as fact. Replace with the valence rule and a pointer to spec v18 Decision 2. A stale comment asserting the opposite of the code is worse than no comment.
- [ ] **Step 9: Run** `npx ng test` (whole suite — the quality-token rename touches components) and `python scripts/testrun.py full`. Both green.
- [ ] **Step 10: Commit** `feat(tokens): the modern-fintech palette and a three-step motion scale`

**Trap: CSS custom properties do not work in media-query conditions.** `@media (min-width: var(--bp-md))` silently never matches. The breakpoints in SR23 are therefore literal `px` values in the media queries, with the canonical list documented in a comment here and in one TS constant. Do not add `--bp-*` tokens; they would look usable and would not be.

---

### Task SR3: Hex-literal audit

**Owns:** `docs/superpowers/results/2026-08-13-hex-literal-audit.md`, plus whichever `frontend/src/**` files carry literals
**Blocked by:** SR2

The palette only holds if nothing bypasses it.

- [ ] **Step 1: Enumerate.** `cd frontend && git grep -nE "#[0-9a-fA-F]{3,8}\b" -- src | grep -v "src/styles/tokens.css"`
- [ ] **Step 2:** For each hit, either replace it with the token carrying that meaning, or record it in the audit doc with the reason it is exempt. There are only two legitimate exemption classes: colours inside an SVG asset that is artwork rather than UI, and the chart theme's own required literals (SR35 replaces those with token reads).
- [ ] **Step 3: Verify** the grep from Step 1 returns only lines listed in the audit doc.
- [ ] **Step 4:** `npx ng test` and `python scripts/testrun.py full` green.
- [ ] **Step 5: Commit** `refactor(frontend): every colour comes from a token`

---

### Task SR4: Cockpit → Dashboard, end to end

**Owns:** `swingbot/admin/api_v1/cockpit.py`→`dashboard.py`, `swingbot/admin/api_v1/__init__.py`, `swingbot/admin/spa.py`, `frontend/src/app/workspaces/cockpit/`→`dashboard/`, `frontend/src/app/stores/cockpit.store.ts`→`dashboard.store.ts`, `frontend/src/app/stores/cockpit.store.spec.ts`→`dashboard.store.spec.ts`, `frontend/src/app/api/api-client.ts`, `frontend/src/app/api/models.ts`, `frontend/src/app/app.routes.ts`, `frontend/src/app/shell/shell.ts`, `tests/admin/test_api_v1_cockpit.py`→`test_api_v1_dashboard.py`
**Blocked by:** SR3

Spec Decision 7.

- [ ] **Step 1: Move the files with `git mv`**, not create-and-delete — the rename must show as a rename in the log or the diff is unreviewable.

```bash
git mv swingbot/admin/api_v1/cockpit.py swingbot/admin/api_v1/dashboard.py
git mv tests/admin/test_api_v1_cockpit.py tests/admin/test_api_v1_dashboard.py
git mv frontend/src/app/workspaces/cockpit frontend/src/app/workspaces/dashboard
git mv frontend/src/app/workspaces/dashboard/cockpit.ts frontend/src/app/workspaces/dashboard/dashboard.ts
git mv frontend/src/app/stores/cockpit.store.ts frontend/src/app/stores/dashboard.store.ts
git mv frontend/src/app/stores/cockpit.store.spec.ts frontend/src/app/stores/dashboard.store.spec.ts
```

- [ ] **Step 2: Rewrite the identifiers.** `git grep -niE "cockpit" -- swingbot frontend/src tests docs` and work the list. `CockpitStore`→`DashboardStore`, `CockpitComponent`→`DashboardComponent`, `CockpitPayload`→`DashboardPayload`, route `/cockpit`→`/dashboard`, endpoint `/api/v1/cockpit`→`/api/v1/dashboard`, `ApiClient.cockpit()`→`ApiClient.dashboard()`.
- [ ] **Step 3: Add the redirect** in `app.routes.ts`, above the `/dashboard` route:

```ts
{ path: 'cockpit', redirectTo: 'dashboard', pathMatch: 'prefix' },
```

- [ ] **Step 4: `swingbot/admin/spa.py`** — the workspace prefix list gains `dashboard` and keeps `cockpit`, so a hard refresh on the old URL still serves the SPA, which then client-side redirects. A removed prefix would 404 before Angular ever loads.
- [ ] **Step 5: `tests/admin/conftest.py`** — the `api_v1` reload rules reference module names. Check `_RELOAD_MODULES` and any explicit import of `api_v1.cockpit`.
- [ ] **Step 6: No API alias.** `/api/v1/cockpit` is deleted, not aliased. One consumer, shipped from the same build. Add a test asserting it 404s so the absence is deliberate rather than accidental.
- [ ] **Step 7: Verify** `git grep -niE "cockpit" -- swingbot frontend/src tests` returns only the redirect route, the `spa.py` prefix, and the 404 test.
- [ ] **Step 8:** `python scripts/testrun.py full` and `npx ng test` green; `cd frontend && npx ng build` succeeds.
- [ ] **Step 9: Commit** `refactor(admin): Cockpit is Dashboard, end to end`

---

### Task SR5: Universe → Watchlist, end to end

**Owns:** the same shape as SR4, for `universe`
**Blocked by:** SR4

Spec Decision 7. Same steps as SR4 with `universe`→`watchlist`, `UniverseStore`→`WatchlistStore`, `/universe`→`/watchlist`, `api_v1/universe.py`→`watchlist.py`, `workspaces/universe/`→`workspaces/watchlist/` (both `universe.ts`→`watchlist.ts` and `ticker-detail.ts` moving with it), plus the `cockpit`-style redirect and `spa.py` prefix.

- [ ] **Step 1:** `git mv` the six paths.
- [ ] **Step 2:** Rewrite identifiers via `git grep -niE "universe" -- swingbot/admin frontend/src tests`.
- [ ] **Step 3:** Add `{ path: 'universe', redirectTo: 'watchlist', pathMatch: 'prefix' }`.
- [ ] **Step 4: Leave `SCAN_UNIVERSE` alone.** Spec Decision 7 says so explicitly. Add a one-line comment beside the config `Field` recording that *watchlist* is the UI workspace and the bot's `!watchlist` list, and *universe* survives only as the name of the scan-breadth setting — so a later reader does not "finish" this rename.
- [ ] **Step 5: Verify** `git grep -niE "\buniverse\b" -- swingbot/admin frontend/src tests` returns only the redirect, the `spa.py` prefix, the 404 test, and `SCAN_UNIVERSE` references.
- [ ] **Step 6:** Full pytest + vitest + `ng build` green.
- [ ] **Step 7: Commit** `refactor(admin): Universe is Watchlist, end to end`

---

### Task SR6: Identity assets

**Owns:** `frontend/public/`, `frontend/src/index.html`, `frontend/angular.json`
**Blocked by:** SR5

Spec Decision 8.

- [x] **Step 1: Copy** — not move; Jinja still serves its own copies until NG57. **`favicon.png` deliberately excluded** — see the note under step 6.

```bash
cp swingbot/admin/static/images/{favicon.svg,favicon.png,favicon.ico,favicon-16.png,favicon-32.png,apple-touch-icon.png,bot-profile.png,bot-profile@2x.png} frontend/public/
```

- [x] **Step 2: Replace the `<link rel="icon">` line** in `frontend/src/index.html` with the full set, SVG first:

```html
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="favicon-16.png">
  <link rel="icon" type="image/x-icon" href="favicon.ico">
  <link rel="apple-touch-icon" href="apple-touch-icon.png">
```

- [x] **Step 3:** Update the inline `<style>` fallback background from `#000000` to `#0a0b10` so a slow bundle load paints the new ground colour, not the old one.
- [x] **Step 4:** Confirm `angular.json`'s `assets` block copies all of `public/` into the build output. It does by default in Angular 21; verify rather than assume, because a missing favicon fails silently.
- [x] **Step 5: Verify** `cd frontend && npx ng build` then `ls dist/*/browser/favicon.svg` exists.
- [x] **Step 6: Commit** `feat(frontend): the guinea pig comes back`

**Deviation from step 1, on purpose.** The `cp` list above includes
`favicon.png`, and it should not: that file is the **1.9 MB master** every
other size was generated from, the SPA's `<link>` set never references it, and
only the Jinja templates consume it. Copying it would have put five times the
app's entire initial bundle (313 kB) into `dist/` to be downloaded by nobody.
It stays in `swingbot/admin/static/images/`, where its consumers are. The
built output was checked for its absence, not just for the others' presence.

The inline `#0a0b10` in `index.html` is now the one colour literal SR3's audit
leaves standing — it must paint before any stylesheet exists, so it cannot
read `--bg`. Commented as a copy that has to be kept in sync, since the
symptom of drift is a single frame of the old colour on a cold load.

---

## Phase 0 gate

- [x] `python scripts/testrun.py full` → `0 failed` — 1679 passed
- [x] `cd frontend && npx ng test` → green — 336 passed across 20 files
- [x] `npx ng build` → succeeds — 313 kB initial, `<base href="/app/">` intact
- [x] Load the SPA, click every nav entry, confirm no 404 and the new palette is live — all six render, zero console errors, zero 4xx; `--bg` resolves to `#0a0b10` and Inter is loading. `scripts/smoke_spa.py` passes 23/23 against a real server on the built bundle, including all five favicons resolving from `/app/`.
- [ ] Merge `worktree-spa-refresh` → `main` (check main-tree `git status` first)

**Two things the walk found, both in the verification rather than the app:**

`scripts/smoke_spa.py` had gone stale in two places the moment SR4/SR5 landed.
Its workspace list still read `cockpit`/`universe`, so it kept passing while
testing neither `/dashboard` nor `/watchlist` — the two routes those tasks
created. And it asserted `/` redirects to `/cockpit`, which the app had
correctly changed to `/dashboard`. Both fixed: the list now covers the new
names plus the legacy ones (dropping those 404s an old bookmark before Angular
can redirect it), and the front-door check now asserts the *property* — that
`/` redirects and wherever it lands serves the app — rather than a hardcoded
destination that goes stale on the next rename.

A hard load of `/risk` renders empty. That is `spa.py:register`'s documented
collision — Jinja owns `/risk` until NG57 — not a regression. In-app
navigation to Risk works. It self-heals when the Jinja routes go.

---

# Phase 1 — Tables (SR7–SR19)

Spec Decisions 4, 5 and 6.

### Task SR7: `TradeRow` gains the status fields

**Owns:** `swingbot/admin/api_v1/trades.py`, `tests/admin/test_api_v1_trades.py`
**Produces:** these five fields on every `TradeRow`, consumed by SR11 and SR16:

```
progress_pct    float | null   0..100; 0 = stop, 100 = target. null when no live price.
entry_pct       float | null   0..100; where the entry tick sits on that scale.
progress_band   "toward_stop" | "neutral" | "toward_target" | null
blink_seconds   float | null   pulse period, 0.6..2.2
status_label    string         human-readable, drives the tooltip
```

**Blocked by:** Phase 0

Spec Decision 5. **The maths already exists — reuse it.**

- [ ] **Step 1: Write the failing contract test** in `tests/admin/test_api_v1_trades.py`:

```python
def test_open_trade_row_carries_the_status_bar_fields(client, seeded_open_trade):
    row = client.get("/api/v1/trades?status=open").get_json()["items"][0]
    assert 0.0 <= row["progress_pct"] <= 100.0
    assert 0.0 <= row["entry_pct"] <= 100.0
    assert row["progress_band"] in {"toward_stop", "neutral", "toward_target"}
    assert 0.6 <= row["blink_seconds"] <= 2.2
    assert isinstance(row["status_label"], str) and row["status_label"]


def test_status_fields_are_null_without_a_live_price(client, seeded_open_trade, no_prices):
    row = client.get("/api/v1/trades?status=open").get_json()["items"][0]
    assert row["progress_pct"] is None
    assert row["progress_band"] is None
    assert row["blink_seconds"] is None
    # The label always exists -- it is what the degraded cell shows.
    assert row["status_label"]


def test_a_short_reaching_its_target_reads_100_not_0(client, seeded_short_at_target):
    """Direction handling is the one thing a naive implementation gets wrong:
    for a short the target is BELOW entry, so a falling price is progress."""
    row = client.get("/api/v1/trades?status=open").get_json()["items"][0]
    assert row["progress_pct"] > 95.0
    assert row["progress_band"] == "toward_target"
```

- [ ] **Step 2: Run and watch it fail** — `python scripts/testrun.py file tests/admin/test_api_v1_trades.py`. Expected: `KeyError: 'progress_pct'`.
- [ ] **Step 3: Add the helper** to `swingbot/admin/api_v1/trades.py`. It calls the two existing implementations and adds nothing of its own:

```python
from swingbot.core.performance import trade_proximity


def _status_fields(row: dict, price: float | None) -> dict:
    """The status-bar numbers, from the two functions that already own them.

    `trade_proximity` (core/performance.py) owns urgency and the label -- it
    is the same computation the bot's own near-close alerts use, so a second
    implementation here could make the UI and the alerts disagree about how
    close a trade is to its stop. The 0..100 position is the dashboard's
    (admin/dashboard.py, `pos_pct`), restated here rather than imported
    because that module builds a whole Jinja view model to produce it.

    No colour is returned. The band names which pair of tokens the client
    interpolates between; the palette lives in tokens.css. See spec v18
    Decision 5.
    """
    entry, sl, tp = row.get("entry"), row.get("stop_loss"), row.get("target")
    direction = row.get("direction") or "bullish"
    label_only = {"progress_pct": None, "entry_pct": None, "progress_band": None,
                  "blink_seconds": None, "status_label": "No live price"}

    if price is None or not all(isinstance(v, (int, float)) for v in (entry, sl, tp)):
        return label_only

    prox = trade_proximity(direction, entry, sl, tp, price)
    is_bull = direction == "bullish"
    span = (tp - sl) if is_bull else (sl - tp)
    if span <= 0:                      # malformed record: stop on the wrong side
        return label_only

    pos = ((price - sl) if is_bull else (sl - price)) / span * 100
    ent = ((entry - sl) if is_bull else (sl - entry)) / span * 100
    band = ("toward_target" if prox["proximity"] > 0.15
            else "toward_stop" if prox["proximity"] < -0.15
            else "neutral")
    return {
        "progress_pct": max(0.0, min(100.0, round(pos, 1))),
        "entry_pct": max(0.0, min(100.0, round(ent, 1))),
        "progress_band": band,
        "blink_seconds": prox["blink_seconds"],
        "status_label": prox["label"],
    }
```

- [ ] **Step 4: Call it from `_attach_current_prices`**, which is already the one place a row meets its live price, and merge the result into the row. Do not call it from `_row_from_trade` / `_row_from_plan` — those run before prices are fetched.
- [ ] **Step 5:** For PENDING / CLOSED / CANCELLED / EXPIRED rows, return `label_only` with `status_label` set to the status word. There is no position to show for a trade that has not opened or has already closed.
- [ ] **Step 6: Add the fields to the `TRADE_ROW` contract set** in the same test file — `assert_shape` rejects undeclared keys as loudly as missing ones, so an unlisted field fails every other row test.
- [ ] **Step 7: Mirror the fields into `frontend/src/app/api/models.ts`** on the `TradeRow` interface, all nullable.
- [ ] **Step 8: Run** `python scripts/testrun.py full` → `0 failed`.
- [ ] **Step 9: Commit** `feat(api): the status-bar fields on every trade row`

---

### Task SR8: `PlanCell`

**Owns:** `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/ui/plan-cell.spec.ts`
**Produces:** `<sb-plan-cell [entry]="…" [target]="…" [stop]="…" />`
**Blocked by:** Phase 0

Spec Decision 4.

- [ ] **Step 1: Write the failing test.**

```ts
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { PlanCell } from './plan-cell';

function render(entry: number | null, target: number | null, stop: number | null) {
  const f = TestBed.createComponent(PlanCell);
  f.componentRef.setInput('entry', entry);
  f.componentRef.setInput('target', target);
  f.componentRef.setInput('stop', stop);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('PlanCell', () => {
  it('reads entry -> target / stop for a long', () => {
    expect(render(178, 195, 170).textContent!.replace(/\s+/g, ' ').trim())
      .toBe('178.00 → 195.00 / 170.00');
  });

  it('reads the same way for a short, where the target is the lower number', () => {
    expect(render(178, 162, 186).textContent!.replace(/\s+/g, ' ').trim())
      .toBe('178.00 → 162.00 / 186.00');
  });

  it('colours target and stop by role, not by which is larger', () => {
    const el = render(178, 162, 186);
    expect(el.querySelector('.target')!.className).toContain('target');
    expect(el.querySelector('.stop')!.className).toContain('stop');
  });

  it('renders an em dash for a missing level rather than NaN', () => {
    expect(render(178, null, 170).textContent).toContain('—');
  });

  it('carries the spelled-out tooltip', () => {
    expect(render(178, 195, 170).querySelector('[title]')!.getAttribute('title'))
      .toBe('Entry 178.00 · Target 195.00 · Stop 170.00');
  });
});
```

- [ ] **Step 2: Run and watch it fail** — `npx ng test`. Expected: cannot resolve `./plan-cell`.
- [ ] **Step 3: Implement.**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { num } from './format';

/**
 * Entry, target and stop in one cell — spec v18 Decision 4.
 *
 * Always reads `entry → target / stop`, in that order, for both directions.
 * For a short the target is the lower number and the stop the higher one, so
 * the COLOURS carry which is which, not the positions. Anything that inferred
 * role from magnitude would silently invert on every short.
 */
@Component({
  selector: 'sb-plan-cell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="plan" [title]="tooltip()">
      <span class="entry">{{ fmt(entry()) }}</span>
      <span class="sep">→</span>
      <span class="target">{{ fmt(target()) }}</span>
      <span class="sep">/</span>
      <span class="stop">{{ fmt(stop()) }}</span>
    </span>
  `,
  styles: `
    .plan { font-family: var(--font-mono); font-size: var(--text-table); white-space: nowrap; }
    .entry  { color: var(--text-secondary); }
    .target { color: var(--pos); }
    .stop   { color: var(--neg); }
    .sep    { color: var(--text-faint); margin: 0 var(--space-4); }
  `,
})
export class PlanCell {
  readonly entry = input<number | null>(null);
  readonly target = input<number | null>(null);
  readonly stop = input<number | null>(null);

  protected readonly tooltip = computed(() =>
    `Entry ${this.fmt(this.entry())} · Target ${this.fmt(this.target())} · Stop ${this.fmt(this.stop())}`,
  );

  protected fmt(v: number | null): string {
    return num(v);
  }
}
```

- [ ] **Step 4: Run** `npx ng test` → PASS. If `num(null)` does not already return `—`, fix `format.ts` rather than special-casing here.
- [ ] **Step 5: Commit** `feat(ui): the combined plan cell`

---

### Task SR9: `DirectionArrow`

**Owns:** `frontend/src/app/ui/direction-arrow.ts`, `frontend/src/app/ui/direction-arrow.spec.ts`
**Produces:** `<sb-direction-arrow [direction]="row.direction" />`
**Blocked by:** Phase 0

Spec Decision 4. The one recorded exception to the valence rule.

- [ ] **Step 1: Write the failing test** — assert `▲` with class `long` for `bullish`, `▼` with class `short` for `bearish`, `—` for `null`, and that `title` and `aria-label` both read `Long (bullish)` / `Short (bearish)`. The accessible name is not optional here: the glyph alone is the entire content of the cell, so without it the column is unreadable to a screen reader.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** — `.long { color: var(--pos); } .short { color: var(--neg); }`, `font-weight: 700`, `font-size: var(--text-subhead)`, `cursor: help`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ui): direction as a glyph`

---

### Task SR10: `ConfidenceCell`

**Owns:** `frontend/src/app/ui/confidence-cell.ts`, `frontend/src/app/ui/confidence-cell.spec.ts`
**Produces:** `<sb-confidence-cell [level]="…" [score]="…" />`
**Blocked by:** Phase 0

Spec Decision 4.

- [ ] **Step 1: Write the failing test** — `Lv4 · 78` when both present; `Lv4` alone when `score` is null (**not** `Lv4 · —`); `—` when level is null; and the badge carries `quality-4` for level 4, `quality-1` for level 1.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement**, mapping level to `var(--quality-N)` via a class per level. Do not index a token name by string interpolation in the template — a level outside 1–5 would produce a `var(--quality-9)` that resolves to nothing and renders invisible text.

```ts
protected readonly band = computed(() => {
  const lv = this.level();
  return lv !== null && lv >= 1 && lv <= 5 ? `q${lv}` : 'q3';
});
```

- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ui): confidence as level and score`

---

### Task SR11: `StatusCell`

**Owns:** `frontend/src/app/ui/status-cell.ts`, `frontend/src/app/ui/status-cell.spec.ts`
**Produces:** `<sb-status-cell [row]="row" />`
**Blocked by:** SR7 (needs the row fields), SR2

Spec Decision 5. Three parts: dot, bar with entry tick, percentage.

- [ ] **Step 1: Write the failing test.**

```ts
describe('StatusCell', () => {
  const live = {
    status: 'ACTIVE', progress_pct: 62, entry_pct: 40,
    progress_band: 'toward_target', blink_seconds: 1.4, status_label: 'Trending toward target',
  };

  it('renders dot, bar and percentage for a live position', () => {
    const el = render(live);
    expect(el.querySelector('.dot')).toBeTruthy();
    expect(el.querySelector('.fill')!.getAttribute('style')).toContain('62%');
    expect(el.querySelector('.tick')!.getAttribute('style')).toContain('40%');
    expect(el.textContent).toContain('62%');
  });

  it('drives the pulse period from blink_seconds', () => {
    expect(render(live).querySelector('.dot')!.getAttribute('style')).toContain('1.4s');
  });

  it('falls back to the status chip when there is no live price', () => {
    const el = render({ ...live, progress_pct: null, progress_band: null, blink_seconds: null });
    expect(el.querySelector('.fill')).toBeNull();
    expect(el.textContent).toContain('no price');
  });

  it('shows the chip alone for a trade that has not opened', () => {
    const el = render({ ...live, status: 'PENDING', progress_pct: null, progress_band: null });
    expect(el.querySelector('.fill')).toBeNull();
    expect(el.textContent).toContain('PENDING');
  });

  it('clamps a price beyond the target to a full bar', () => {
    expect(render({ ...live, progress_pct: 100 }).querySelector('.fill')!.getAttribute('style'))
      .toContain('100%');
  });
});
```

- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement.** The bar fill interpolates between the band's two tokens — this is the client-side half of spec Decision 5's refinement:

```css
.fill {
  height: 100%;
  transition: width var(--dur-base) var(--ease-out);
}
.fill.toward_target { background: linear-gradient(90deg, var(--text-muted), var(--pos)); }
.fill.toward_stop   { background: linear-gradient(90deg, var(--neg), var(--text-muted)); }
.fill.neutral       { background: var(--text-muted); }

.dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor;
  animation: pulse var(--blink) ease-in-out infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
```

with `--blink` bound from `blink_seconds` as an inline style, and the dot's `color` set to the band's token.

- [ ] **Step 4:** The four degraded states from spec Decision 5's table each render the existing `StatusIndicator` chip. Import it; do not reimplement it.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat(ui): the SL→TP status cell`

---

### Task SR12: Density model and preference keys

**Owns:** `frontend/src/app/ui/data-table/data-table.types.ts`, `frontend/src/app/stores/preferences.store.ts`, `frontend/src/app/stores/preferences.store.spec.ts`, `frontend/src/app/ui/table-prefs.ts`, `frontend/src/app/ui/table-prefs.spec.ts`
**Produces:** the preference read/write API every later table task uses:

```ts
type Density = 'compact' | 'full';

readTableDensity(prefs, tableId): Density                       // default 'compact'
readTableColumns(prefs, tableId, density, baseline): string[]   // tolerant, ordered
readTablePerPage(prefs, tableId): number                        // default 25
writeTableDensity / writeTableColumns / writeTablePerPage
```

**Blocked by:** Phase 0

Spec Decision 4, "Persistence", and the reversal of *"`visible` columns carry no order"*.

- [ ] **Step 1: Write the failing test** for the tolerant read — this is the whole reason the reversal is safe:

```ts
describe('readTableColumns', () => {
  const baseline = ['num', 'status', 'ticker'];

  it('returns the baseline when nothing is stored', () => {
    expect(readTableColumns({}, 'trades', 'compact', baseline)).toEqual(baseline);
  });

  it('honours a stored order', () => {
    const prefs = { 'tables.trades.compact.columns': ['ticker', 'num', 'status'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline))
      .toEqual(['ticker', 'num', 'status']);
  });

  it('drops a stored key that is no longer a column', () => {
    const prefs = { 'tables.trades.compact.columns': ['ticker', 'deleted_col', 'num'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline)).toEqual(['ticker', 'num']);
  });

  it('appends a baseline column absent from the stored order, never hides it', () => {
    const prefs = { 'tables.trades.compact.columns': ['ticker'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline))
      .toEqual(['ticker', 'num', 'status']);
  });

  it('survives a stored value of the wrong type', () => {
    expect(readTableColumns({ 'tables.trades.compact.columns': 'nonsense' } as never,
                            'trades', 'compact', baseline)).toEqual(baseline);
  });

  it('keeps the two densities independent', () => {
    const prefs = { 'tables.trades.full.columns': ['ticker'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline)).toEqual(baseline);
  });
});
```

- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement `table-prefs.ts`.** The stored order is a *filter and sort over* the baseline, never a parallel list — that is what makes a stale preference degrade instead of breaking:

```ts
export function readTableColumns(
  prefs: Preferences, tableId: string, density: Density, baseline: string[],
): string[] {
  const stored = prefs[`tables.${tableId}.${density}.columns`];
  if (!Array.isArray(stored)) return [...baseline];
  const known = new Set(baseline);
  const ordered = stored.filter((k): k is string => typeof k === 'string' && known.has(k));
  const seen = new Set(ordered);
  return [...ordered, ...baseline.filter((k) => !seen.has(k))];
}
```

- [ ] **Step 4:** Add `Density` to `data-table.types.ts` and a `density` input to `ColumnDef` consumers. `DataTableComponent` itself gains `density` and `visibleColumns` (ordered) inputs.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat(table): density and an ordered, tolerant column preference`

---

### Task SR13: Column picker, per mode

**Owns:** `frontend/src/app/ui/column-picker.ts`, `frontend/src/app/ui/column-picker.spec.ts`
**Blocked by:** SR12

- [ ] **Step 1: Write the failing test** — editing the visible set while in Compact must not change what Full shows; "Reset to default" restores that mode's baseline only; a column pinned by the table (`actions`) never appears in the picker at all.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** — the picker takes `density` and writes through `writeTableColumns(…, density, …)`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(table): the picker edits one density at a time`

---

### Task SR14: Drag-to-reorder

**Owns:** `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/ui/data-table/data-table.spec.ts`
**Blocked by:** SR12

Spec Decision 4, "Reversal recorded".

- [ ] **Step 1: Write the failing test** — a `dragstart` on header B and `drop` on header A reorders the rendered cells to match, emits the new order, and **pinned columns cannot be dragged or dropped onto**.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** with native HTML5 drag events on `<th>` (`draggable="true"`), as the Jinja table did. No drag library — it would be a new dependency for one interaction.
- [ ] **Step 4: Keyboard equivalent.** Left/Right arrow on a focused header moves that column one position, because a mouse-only reorder is unreachable by keyboard and this table is the product's main surface.
- [ ] **Step 5: Delete the "visible columns carry no order" note** from `data-table.types.ts`'s header comment and replace it with a pointer to spec v18 Decision 4. Leaving the old note would contradict the code it sits on.
- [ ] **Step 6: Run** → PASS.
- [ ] **Step 7: Commit** `feat(table): drag-to-reorder returns, with a keyboard path`

---

### Task SR15: Per-page selector

**Owns:** `frontend/src/app/ui/pagination.ts`, `frontend/src/app/ui/pagination.spec.ts`
**Blocked by:** SR12

- [ ] **Step 1: Write the failing test** — options 10 / 25 / 50 / All; `All` emits `0`; the choice persists via `writeTablePerPage`; and **`0` is sent to the API as `per_page=200`**, the collection endpoint's documented cap, not as `0` (which the endpoint rejects).
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(table): per-page selector`

---

### Task SR16: Trades workspace — the new table

**Owns:** `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trades.columns.ts`, `frontend/src/app/workspaces/trades/trades.columns.spec.ts`
**Blocked by:** SR7, SR8, SR9, SR10, SR11, SR12, SR13, SR14, SR15

Spec Decision 4. This is where it all meets.

- [ ] **Step 1: Write the failing test** in `trades.columns.spec.ts`:

```ts
import { COMPACT_COLUMNS, FULL_COLUMNS, PINNED_COLUMNS, tradeColumns } from './trades.columns';

describe('trade column sets', () => {
  it('compact is exactly the spec list', () => {
    expect(COMPACT_COLUMNS).toEqual([
      'num', 'status', 'ticker', 'confidence_level', 'direction',
      'now', 'plan', 'pnl_pct', 'r_multiple', 'opened_at', 'closed_at',
    ]);
  });

  it('full is exactly the spec list', () => {
    expect(FULL_COLUMNS).toEqual([
      'num', 'status', 'ticker', 'confidence_level', 'direction',
      'now', 'plan', 'risk_reward', 'r_multiple', 'strategy', 'horizon',
      'pnl_pct', 'held', 'realized_pnl_amount', 'opened_at', 'closed_at',
    ]);
  });

  it('actions are pinned, not a member of either set', () => {
    expect(PINNED_COLUMNS).toEqual(['actions']);
    expect(COMPACT_COLUMNS).not.toContain('actions');
    expect(FULL_COLUMNS).not.toContain('actions');
  });

  it('every key in both sets exists in tradeColumns()', () => {
    const known = new Set(tradeColumns().map((c) => c.key));
    for (const k of [...COMPACT_COLUMNS, ...FULL_COLUMNS, ...PINNED_COLUMNS]) {
      expect(known, `missing column def: ${k}`).toContain(k);
    }
  });

  it('the plan column is not sortable', () => {
    expect(tradeColumns().find((c) => c.key === 'plan')!.sortable).toBeFalsy();
  });

  it('keeps entry, stop and target available to the picker', () => {
    const known = new Set(tradeColumns().map((c) => c.key));
    for (const k of ['entry', 'stop_loss', 'target']) expect(known).toContain(k);
  });
});
```

- [ ] **Step 2: Run and watch it fail** — `COMPACT_COLUMNS` does not exist.
- [ ] **Step 3: Replace `DEFAULT_TRADE_COLUMNS`** with the three exported constants above, and add the `plan` column def rendering `PlanCell`. Delete `DEFAULT_TRADE_COLUMNS` — leaving it means two answers to "what does this table show".
- [ ] **Step 4: Wire the cell components** into their column defs: `status` → `StatusCell`, `direction` → `DirectionArrow`, `confidence_level` → `ConfidenceCell`, `plan` → `PlanCell`.
- [ ] **Step 5: `status` sorts on `progress_pct`,** with null-progress rows last in **both** directions. Add a test: sorting ascending and descending must both put a no-price row at the end, not cluster it at whichever end zero falls.
- [ ] **Step 6: Add the toolbar** — density toggle, picker, per-page — beside the existing filter and status chips.
- [ ] **Step 7: Default to compact** on first load and for any user with no stored preference.
- [ ] **Step 8: Run** `npx ng test` → green.
- [ ] **Step 9: Commit** `feat(trades): compact and full, with the status bar`

---

### Task SR17: Dashboard adopts the same table

**Owns:** `frontend/src/app/workspaces/dashboard/dashboard.ts`
**Blocked by:** SR16

Spec Decision 6. Reverses workspaces v14 Decision 5.

- [ ] **Step 1: Delete the local four-column `columns` computed** and import `tradeColumns`, `COMPACT_COLUMNS`, `FULL_COLUMNS`, `PINNED_COLUMNS` from the Trades workspace.
- [ ] **Step 2: Pass `tableId="dashboard"`** so density and column choices persist separately from the Trades table's.
- [ ] **Step 3: Add the same toolbar.** Filtering stays fixed to open positions — that is what the panel is.
- [ ] **Step 4: Write the test** asserting the two tables share column definitions but not preferences: writing `tables.dashboard.compact.columns` must not change what Trades renders.
- [ ] **Step 5: Run** `npx ng test` → green.
- [ ] **Step 6: Commit** `feat(dashboard): the same table as Trades`

---

### Task SR18: Row expansion, narrowed

**Owns:** `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/workspaces/trades/trades.ts`
**Blocked by:** SR16

Spec Decision 4, "Row expansion stays".

- [ ] **Step 1: Write the failing test** — the expansion renders exactly the columns *not* in the current density's visible set, plus the three fields that are never columns (target sources, leg breakdown, note). Switching density changes the expansion's contents accordingly.
- [ ] **Step 2: Run and watch it fail** — today it renders a fixed four-group grid.
- [ ] **Step 3: Implement** as a computed over `visibleColumns` and the full `columns` list.
- [ ] **Step 4: Keep the label/value grid markup** — SR24 reuses it verbatim for the phone card, so changing its shape here has a second consumer.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat(table): the expansion shows what the current mode hides`

---

### Task SR19: Phase 1 QA walk

**Owns:** `docs/superpowers/results/2026-08-13-spa-refresh-qa.md`
**Blocked by:** SR18

- [ ] **Step 1:** Write the checklist section for Phase 1: both tables in both modes; the plan cell on a long and on a short; the status bar on a trade near TP, near SL, at entry, with no price, PENDING, and CLOSED; picker independence across modes; drag-reorder by mouse and by keyboard; per-page including All; preferences surviving a reload and a second browser.
- [ ] **Step 2: Walk it** against a running SPA and record the result of each line — `PASS`, or the defect.
- [ ] **Step 3:** Fix any defect found, as its own commit, and re-walk the affected lines.
- [ ] **Step 4: Commit** `docs(qa): phase 1 walked`

---

## Phase 1 gate

- [ ] `python scripts/testrun.py full` → `0 failed`; `npx ng test` green; `ng build` succeeds
- [ ] Every checklist line in SR19 recorded `PASS`
- [ ] Merge to `main`

---

# Phase 2 — Shell and responsive (SR20–SR31)

Spec Decisions 8 and 9.

### Task SR20: Icon sprite

**Owns:** `frontend/src/app/ui/icon.ts`, `frontend/src/app/ui/icon.spec.ts`
**Produces:** `<sb-icon name="trades" />`, names: `dashboard` `trades` `analytics` `watchlist` `risk` `system` `collapse` `expand` `profile` `signout` `menu`
**Blocked by:** Phase 1

- [ ] **Step 1: Write the failing test** — every name in the union renders an `<svg>`; an unknown name renders nothing and does not throw; the svg uses `currentColor` for stroke and carries `aria-hidden="true"` (the label is always on the parent control).
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** as one component with a `Record<IconName, string>` of inline path data. Stroke-based, `viewBox="0 0 16 16"`, `stroke-width="1.5"`, `fill="none"`. **Hand-authored — no icon package, no font, no CDN**, per the global constraint.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ui): the icon set`

---

### Task SR21: Collapsible sidebar

**Owns:** `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.spec.ts`
**Blocked by:** SR20, SR23

Spec Decision 8.

- [ ] **Step 1: Write the failing test** — expanded is 200px and rail is 52px; the toggle flips and persists through `PreferencesStore` under `shell.sidebar`; crossing below 1024px forces the rail regardless of the stored value; crossing below 640px switches to overlay and a navigation closes it; a railed entry keeps its `aria-label`.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement.** The automatic state and the explicit toggle compose as spec Decision 8 says: the user's toggle wins *within* a breakpoint; crossing one re-applies the automatic state.
- [ ] **Step 4: Add each nav entry's icon** from SR20, and the brand mark's avatar (`bot-profile.png`, `srcset` at 2x) which shrinks to the avatar alone on the rail.
- [ ] **Step 5:** Transition `grid-template-columns` at `var(--dur-slow) var(--ease-spring)`.
- [ ] **Step 6: Run** → PASS.
- [ ] **Step 7: Commit** `feat(shell): the sidebar collapses to an icon rail`

---

### Task SR22: Profile menu

**Owns:** `frontend/src/app/shell/profile-menu.ts`, `frontend/src/app/shell/profile-menu.spec.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/login/`
**Blocked by:** SR21

Spec Decision 8.

- [ ] **Step 1: Write the failing test** — the avatar button opens the menu; Escape and an outside click close it; "Sign out" calls the same `logout()` the sidebar button called; focus returns to the trigger on close.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement**, and **remove the `.logout` button from the sidebar** — two sign-out controls is worse than either one alone.
- [ ] **Step 4: Add the avatar to the login card**, above the form.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat(shell): the profile menu`

---

### Task SR23: Breakpoints, spacing and the overflow guard

**Owns:** `frontend/src/styles/tokens.css`, `frontend/src/styles.css`, `frontend/src/app/ui/breakpoints.ts`, `frontend/src/app/ui/breakpoints.spec.ts`, `frontend/src/app/ui/layout.ts`
**Produces:** `BREAKPOINTS = { sm: 640, md: 1024, lg: 1440, xl: 1920 }` and a `viewport()` signal
**Blocked by:** Phase 1

Spec Decision 9.

- [ ] **Step 1: Write the failing test** for the boundary arithmetic — 639 is `xs`, 640 is `sm`, 1023 is `sm`, 1024 is `md`, 1439 is `md`, 1440 is `lg`, 1919 is `lg`, 1920 is `xl`. Off-by-one at a breakpoint is the classic defect and it is invisible until someone resizes to exactly that width.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement `breakpoints.ts`** — the literal values, and a `viewport()` signal fed by one `matchMedia` listener per breakpoint (not a `resize` handler, which fires continuously).
- [ ] **Step 4: Apply the spacing changes** — workspace padding 20px → 14px below 1440px; panel grid `repeat(auto-fit, …)` counts per range from spec Decision 9's table; panel header top margin removed; toolbar row and table header merged into one band.
- [ ] **Step 5: Add the content max-width** of 1760px at ≥1920.
- [ ] **Step 6: Add the overflow guard** to `styles.css`:

```css
html, body { overflow-x: hidden; }
.workspace { min-width: 0; }
```

and confirm every wide surface already sits inside an `overflow-x: auto` container. `body { overflow-x: hidden }` hides the symptom; the `min-width: 0` is what actually lets a grid child scroll instead of stretching its parent. Both are needed.

- [ ] **Step 7:** Restate the breakpoint values in `tokens.css`'s header comment with the note from SR2 about why they are not custom properties.
- [ ] **Step 8: Run** → PASS.
- [ ] **Step 9: Commit** `feat(layout): four breakpoints and tighter spacing`

---

### Task SR24: Card mode for tables

**Owns:** `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/ui/data-table/data-table.spec.ts`
**Blocked by:** SR23, SR18

Spec Decision 9, "The phone table".

- [ ] **Step 1: Write the failing test** — below 640px the component renders one `.card` per row and no `<table>`; the card heading is ticker plus direction; the status bar spans the card's width; the rest of the *compact* set renders as label/value pairs; row actions become full-width buttons; sort and pagination still work; at 640px and above the table returns.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement as a rendering mode of `DataTableComponent`,** switched on `viewport()`. **Not a second component** — same column defs, same sort, same pagination. A separate mobile table drifts from the desktop one within two changes.
- [ ] **Step 4: Reuse SR18's label/value grid markup** for the card body.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat(table): cards below 640px`

---

### Tasks SR25–SR30: Per-workspace responsive passes

**Blocked by:** SR23, SR24 (SR25 and SR26 additionally by SR21)
**These six run concurrently.** Each owns only its own workspace directory.

Each task follows the same five steps; the differences are in what each workspace's widest surface is.

| Task | Workspace | `Owns:` | The surface that will break first |
|---|---|---|---|
| **SR25** | Dashboard | `frontend/src/app/workspaces/dashboard/` | the three primary metric cards side by side |
| **SR26** | Trades + trade detail | `frontend/src/app/workspaces/trades/` | the tab bar, and the detail view's four-panel grid |
| **SR27** | Analytics | `frontend/src/app/workspaces/analytics/` | the strategy registry table and the 10-horizon heatmap |
| **SR28** | Risk | `frontend/src/app/workspaces/risk/` | the exposure table and the heat gauge |
| **SR29** | System | `frontend/src/app/workspaces/system/` | the Settings form's two-column layout and the log viewer |
| **SR30** | Watchlist | `frontend/src/app/workspaces/watchlist/` | the ticker grid and the ticker-detail chart |

- [ ] **Step 1: Write the failing test** — at each of the four viewport widths the workspace renders without the named surface exceeding its container. Assert on the component's computed layout class per breakpoint, not on pixel measurements: jsdom does not lay out, so a width assertion there is theatre.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** the reflow per spec Decision 9's table — panel columns per range, and the workspace's widest surface into an `overflow-x: auto` container if it is not already.
- [ ] **Step 4: Check in a real browser** at 390 / 768 / 1280 / 1920. `document.documentElement.scrollWidth <= window.innerWidth` must hold at all four. Record the four numbers in the task's commit message.
- [ ] **Step 5: Commit** `feat(<workspace>): responsive at four widths`

---

### Task SR31: Phase 2 QA walk

**Owns:** `docs/superpowers/results/2026-08-13-spa-refresh-qa.md`
**Blocked by:** SR25–SR30, SR22

- [ ] **Step 1:** Add the Phase 2 checklist: every workspace at 390 / 768 / 1280 / 1920; sidebar expanded, railed, overlay; auto-collapse crossing 1024 and 640 in both directions; the profile menu by mouse and by keyboard; the avatar in all four places; no horizontal document scroll anywhere.
- [ ] **Step 2: Walk it,** recording each line.
- [ ] **Step 3:** Fix defects as their own commits and re-walk.
- [ ] **Step 4: Commit** `docs(qa): phase 2 walked`

---

## Phase 2 gate

- [ ] Full pytest, vitest, `ng build` green
- [ ] `scrollWidth <= innerWidth` on every workspace at all four widths
- [ ] Merge to `main`

---

# Phase 3 — The chart (SR32–SR40)

Spec Decision 10. **SR34 is a risk gate — read its note before planning any work after it.**

### Task SR32: Extract the chart geometry

**Owns:** `swingbot/core/charts/chart_geometry.py`, `swingbot/core/charts/chart_strategy_overlay.py`, `tests/test_chart_geometry.py`
**Produces:** `overlay_geometry(df, side, sources, **ctx) -> dict | None` — the typed shapes in spec Decision 10's table, as plain JSON-serialisable dicts.
**Blocked by:** Phase 2

The one task in this plan that touches code the bot depends on.

- [ ] **Step 1: Capture the baseline.** Render the PNG for a fixed set of fixture trades — one per overlay kind (`trendline`, `fib_fan`, `fvg_zone`, `curve`, `horizontal`) plus one with no drawable source — and hash each file.

```bash
python scripts/render_chart_fixtures.py --out /tmp/chart-baseline
sha256sum /tmp/chart-baseline/*.png > /tmp/chart-baseline/SHA256
```

Write `scripts/render_chart_fixtures.py` as part of this step if it does not exist; it is the acceptance instrument for the whole task.

- [ ] **Step 2: Write the failing test** in `tests/test_chart_geometry.py` — `overlay_geometry` returns the documented dict for each fixture, and `None` when nothing is drawable.
- [ ] **Step 3: Run and watch it fail.**
- [ ] **Step 4: Extract.** Move the *geometry* computation out of `chart_strategy_overlay.py` into `chart_geometry.py`, returning data. Leave the *drawing* in place, rewritten to consume that data. The dispatcher (`_pick_primary_source`) moves with the geometry — which source wins is a decision about the data, not about matplotlib.
- [ ] **Step 5: Re-render and diff.**

```bash
python scripts/render_chart_fixtures.py --out /tmp/chart-after
sha256sum -c /tmp/chart-baseline/SHA256 --quiet   # run against /tmp/chart-after
```

**Every hash must match.** A single differing byte means the refactor changed output and the task is not done. If matplotlib's non-determinism makes hashing infeasible, fall back to a per-pixel comparison with zero tolerance — but try the hash first; these renders have a fixed seed (`trade_chart.py` sets one deliberately).

- [ ] **Step 6:** `python scripts/testrun.py full` → `0 failed`.
- [ ] **Step 7: Commit** `refactor(charts): geometry as data, with byte-identical output`

---

### Task SR33: The chart-data endpoint

**Owns:** `swingbot/admin/api_v1/market.py`, `tests/admin/test_api_v1_market.py`
**Produces:** `GET /api/v1/market/chart/<trade_id>?window=<bars>` with spec Decision 10's payload.
**Blocked by:** SR32

- [ ] **Step 1: Write the failing contract test** — the exact top-level key set (`ohlcv`, `indicators`, `volume_profile`, `levels`, `overlay`, `currency`); `overlay` is `null` for a trade with no `target_sources`; an unknown `trade_id` is a 404 in the v1 error shape; a `window` outside 20–500 is a `400 invalid`, not a clamp.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement**, composing existing pieces: the OHLCV loader `market.py` already uses, `swingbot.core.indicators` for MACD/RSI/Keltner, `chart_volume_profile` for the bins, the trade's own levels, and SR32's `overlay_geometry`.
- [ ] **Step 4: NO-LOOKAHEAD.** Indicators are computed over the *loaded* window and then sliced to the *visible* window — never computed over the visible slice alone, which would change every value near its left edge. Add a test comparing the last RSI value across two different window sizes: they must be equal.
- [ ] **Step 5: Add the TS interfaces** to `frontend/src/app/api/models.ts`, with `shape` as a discriminated union on `kind`.
- [ ] **Step 6: Run** `python scripts/testrun.py full` → `0 failed`.
- [ ] **Step 7: Commit** `feat(api): the chart-data endpoint`

---

### Task SR34: Primitive spike — the risk gate

**Owns:** `frontend/src/app/ui/chart/primitives/box-primitive.ts`, `frontend/src/app/ui/chart/primitives/box-primitive.spec.ts`
**Blocked by:** Phase 2

**This task exists to find out whether the rest of the phase is possible.** `lightweight-charts` has no native shape support; SR37–SR39 all depend on the v5 series-primitive API being able to draw arbitrary geometry in price/time space.

- [ ] **Step 1:** Implement one `ISeriesPrimitive` that draws a filled, bordered rectangle between two timestamps and two prices — the `fvg_zone` shape, and the simplest of the five.
- [ ] **Step 2: Verify in a browser** that it renders at the correct coordinates, stays anchored while panning and zooming, and survives a series data update.
- [ ] **Step 3: Record the outcome** in `docs/superpowers/results/2026-08-13-chart-primitive-spike.md`: the API used, whether coordinates convert cleanly, and the redraw cost with 500 bars on screen.
- [ ] **Step 4 — THE GATE:**
  - **If it works:** proceed to SR35. SR37–SR39 use this file as their template.
  - **If it does not:** **stop the phase.** Do not attempt SR37–SR39. Write up what failed and take the fallback decision — a `<canvas>` overlay positioned over the chart and synchronised to its coordinate system via `timeScale().timeToCoordinate()` and `priceToCoordinate()` — as an amendment to this plan, with its own task list. That decision belongs at this point, on evidence, not four tasks later on a sunk cost.
- [ ] **Step 5: Commit** `feat(chart): a series primitive, proven`

---

### Task SR35: Chart scaffold — panes, candles, volume

**Owns:** `frontend/src/app/ui/chart/trade-chart.ts`, `frontend/src/app/ui/chart/chart-theme.ts`, `frontend/src/app/stores/chart.store.ts`, `frontend/src/app/stores/chart.store.spec.ts`
**Blocked by:** SR33, SR34

- [ ] **Step 1: Write the failing store test** — `ChartStore` loads from the SR33 endpoint, exposes `loading` / `error` / `data`, and refetches on a `trade` event.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement the store**, then the component: three panes (price+volume, MACD, RSI), candles and the volume histogram on pane 0. Panes are created empty at mount so later tasks add series without restructuring.
- [ ] **Step 4: `chart-theme.ts` reads the CSS tokens** via `getComputedStyle(document.documentElement).getPropertyValue('--pos')` rather than repeating hex values — this is the file SR3's audit exempted, and this step is what removes the exemption.
- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** `feat(chart): three panes, candles and volume`

---

### Task SR36: Plan lines and risk/reward shading

**Owns:** `frontend/src/app/ui/chart/plan-lines.ts`, `frontend/src/app/ui/chart/plan-lines.spec.ts`
**Blocked by:** SR35

- [ ] **Step 1: Write the failing test** — five price lines (entry, stop, target1, target2, working stop) with the right token colours and axis labels; `target2` and `working_stop` are omitted when null rather than drawn at zero; the risk band spans entry→stop in `--neg-soft` and the reward band entry→target in `--pos-soft`.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** — `createPriceLine` for the lines (it gives the TradingView-style axis tag for free), SR34's box primitive for the two bands.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(chart): plan levels and the risk/reward bands`

---

### Task SR37: MACD and RSI panes

**Owns:** `frontend/src/app/ui/chart/indicator-panes.ts`, `frontend/src/app/ui/chart/indicator-panes.spec.ts`
**Blocked by:** SR35

- [ ] **Step 1: Write the failing test** — MACD line, signal line and a histogram coloured per bar by sign, plus a zero line; RSI with 70 / 50 / 30 reference lines; a pane is **omitted entirely** when its series is absent from the payload, never drawn empty.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(chart): the MACD and RSI panes`

---

### Task SR38: Keltner channels and volume profile

**Owns:** `frontend/src/app/ui/chart/overlays-basic.ts`, `frontend/src/app/ui/chart/overlays-basic.spec.ts`
**Blocked by:** SR35, SR34

- [ ] **Step 1: Write the failing test** — the Keltner upper and lower bands render as two line series in `--info` at reduced opacity; the volume profile renders as horizontal bars along the left edge, scaled to the widest bin, and is omitted when there is insufficient history.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** — Keltner as two line series; the profile as an SR34-style primitive, since it is not a time-series and no built-in series type can express it.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(chart): Keltner bands and the volume profile`

---

### Task SR39: The strategy overlay

**Owns:** `frontend/src/app/ui/chart/strategy-overlay.ts`, `frontend/src/app/ui/chart/strategy-overlay.spec.ts`, `frontend/src/app/ui/chart/primitives/`
**Blocked by:** SR34, SR35

The layer that explains why the trade exists.

- [ ] **Step 1: Write the failing test** — one case per `kind`, asserting the primitive chosen and its anchor coordinates:
  - `trendline` → a two-point line plus a diamond marker at each pivot
  - `fib_fan` → one ray per ratio from the shared origin
  - `fvg_zone` → SR34's box
  - `curve` → a polyline through the points
  - `horizontal` → a bounded segment, not a full-width price line
  - an unknown `kind` → draws nothing and does not throw (a new overlay type added server-side must degrade, not crash the chart)
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement** one primitive per kind under `primitives/`, and a dispatcher that switches on `kind`. Overlay colour is `--pos` when `side === "target"` and `--neg` when `side === "stop"`, matching the PNG's fixed accent-per-side rule.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(chart): the confirmed-strategy overlay`

---

### Task SR40: Degraded states and the chart QA walk

**Owns:** `frontend/src/app/workspaces/trades/trade-detail.ts`, `docs/superpowers/results/2026-08-13-spa-refresh-qa.md`
**Blocked by:** SR36, SR37, SR38, SR39

- [ ] **Step 1: Write the failing test** for spec Decision 10's three degraded states — a failed request renders an empty state naming the reason with a retry (never a blank pane); `overlay: null` draws candles, indicators and plan lines only; a missing indicator omits its pane.
- [ ] **Step 2: Run and watch it fail.**
- [ ] **Step 3: Implement**, and replace the trade detail's Chart tab with `TradeChart`.
- [ ] **Step 4: Compare against the PNG.** For each of SR32's fixture trades, put the rendered chart beside the generated image and confirm every level, band and overlay sits at the same price. Record the comparison in the QA doc. This is the only check that catches a coordinate-conversion error, which unit tests cannot see.
- [ ] **Step 5: Walk the Phase 3 checklist**, recording each line.
- [ ] **Step 6: Commit** `feat(chart): degraded states, and the walk against the PNG`

---

## Phase 3 gate

- [ ] Full pytest, vitest, `ng build` green
- [ ] Chart fixture hashes still match SR32's baseline
- [ ] Every fixture's interactive chart matches its PNG level-for-level
- [ ] Merge to `main`

---

# Phase 4 — Parity (SR41–SR48)

Spec Decision 11.

### Tasks SR41–SR45: The template audit

**Blocked by:** Phase 3
**These five run concurrently.** Each owns one results file; none touches code.

| Task | Templates | `Owns:` |
|---|---|---|
| **SR41** | `dashboard.html`, `dashboard_fragment.html`, `plans.html`, `_plans_board.html` | `docs/superpowers/results/2026-08-13-parity-1-dashboard.md` |
| **SR42** | `journal.html`, `trade_detail.html`, `_trade_history_rows.html`, `plan_detail.html` | `…/2026-08-13-parity-2-trades.md` |
| **SR43** | `stats.html`, `strategies.html`, `calibration.html`, `_heatmap.html` | `…/2026-08-13-parity-3-analytics.md` |
| **SR44** | `risk.html`, `tuning.html`, `watchlist.html` | `…/2026-08-13-parity-4-risk.md` |
| **SR45** | `settings.html`, `_settings_diff.html`, `logs.html`, `base.html`, `login.html` | `…/2026-08-13-parity-5-system.md` |

Each task, for each of its templates:

- [ ] **Step 1: Enumerate** every control, column, tooltip, chart, computed number and empty state. Read the template *and* the route that renders it — a number computed in `pages.py` and passed in is a feature even if the template only interpolates it.
- [ ] **Step 2: Classify** each as one row of a table:

```markdown
| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Unrealised P&L in account currency | `dashboard_fragment.html:390` | migrated | Trades table, `realized_pnl_amount` column |
| Sizing-mode mismatch warning in tooltip | `dashboard_fragment.html:396` | **missing** | — |
```

Three statuses only: `migrated`, `dropped on purpose` (naming the decision), `missing`. **Nothing may be left unclassified** — an unclassified row is the state this audit exists to eliminate.

- [ ] **Step 3: Check the SPA before writing `missing`.** Grep `frontend/src` for the field or label. The migration moved things between workspaces; a feature that changed home is `migrated`, not missing.
- [ ] **Step 4: Commit** `docs(parity): <group> audited`

---

### Task SR46: Consolidate the gap table

**Owns:** `docs/superpowers/results/2026-08-13-jinja-feature-parity.md`
**Blocked by:** SR41–SR45

- [ ] **Step 1: Merge** the five tables into one, sorted by status then by workspace.
- [ ] **Step 2: Count** and record: total features, migrated, dropped on purpose, missing.
- [ ] **Step 3: Rank the `missing` rows** — *blocks NG57* (a real capability with no equivalent) or *cosmetic* (a tooltip, a label). The ranking is what makes SR47 finite.
- [ ] **Step 4: Delete the five per-group files**; they are superseded and a stale duplicate of a gap table is worse than none.
- [ ] **Step 5: Commit** `docs(parity): the gap table`

---

### Task SR47: Derive the gap-fill tasks

**Owns:** this plan file
**Blocked by:** SR46

The gap list cannot be enumerated before the audit runs, so this task *writes the remaining tasks*.

- [ ] **Step 1:** For each `missing` row ranked *blocks NG57*, append a task `SR48+n` to this plan in the standard format — `Owns:`, `Blocked by:`, failing test, implementation, verification, commit. One task per feature, or one per tightly-coupled group.
- [ ] **Step 2:** For each row ranked *cosmetic*, decide **drop** or **fill** and record the decision in the gap table. A dropped row moves to `dropped on purpose` with this task as the decision.
- [ ] **Step 3: Update the phase table** at the top of this plan with the real Phase 4 task count.
- [ ] **Step 4:** Renumber the release task below to follow the appended ones.
- [ ] **Step 5: Commit** `docs(plan): the gap-fill tasks, derived`

**Acceptance:** every `missing` row in the gap table is either a task in this plan or a recorded decision to drop. Zero rows in neither state.

---

### Task SR48: Release

**Owns:** `VERSION.json`, `README.md`, `docs/superpowers/results/2026-08-13-spa-refresh-qa.md`, `docs/superpowers/plans/2026-08-08-v16-angular-migration.md`
**Blocked by:** every appended gap-fill task

- [ ] **Step 1:** Bump `ui` to `1.2.0` in `VERSION.json` and set `ui_updated`. Minor, not patch: the table model, the palette and the chart are user-visible changes.
- [ ] **Step 2:** Update the README sections the renames and the table changes invalidate — `grep -n "^## " README.md` and read only the sections you need.
- [ ] **Step 3: Walk the full QA checklist** end to end, all four phases, at all four widths. Record it.
- [ ] **Step 4: Release NG57's block** — replace SR1's deferral note in the migration plan with a line stating this plan completed and NG57 may proceed, naming the gap table as the evidence that nothing is lost by deleting the templates.
- [ ] **Step 5:** `python scripts/testrun.py full`, `npx ng test`, `npx ng build` — all green.
- [ ] **Step 6: Commit** `release(ui): 1.2.0 — the SPA refresh`
- [ ] **Step 7:** Merge to `main`.

---

## Definition of done

Spec v18's "Definition of done" is the acceptance list. Every box there maps to a task here:

| Spec item | Task |
|---|---|
| Both tables, compact by default, specified column sets | SR16, SR17 |
| Plan cell, direction glyph, confidence cell | SR8, SR9, SR10 |
| Picker, reorder, per-page, pinned actions | SR13, SR14, SR15, SR16 |
| Status cell with its five states, server-driven | SR7, SR11 |
| New palette and motion scale, no hex literals | SR2, SR3 |
| Renames end to end, with redirects | SR4, SR5 |
| Sidebar rail, persistence, auto-collapse, overlay | SR21, SR23 |
| Avatar in four places | SR6, SR21, SR22 |
| No horizontal scroll at four widths | SR23, SR25–SR30, SR31 |
| The chart's ten layers from one endpoint | SR32–SR40 |
| Parity gap table, every row classified | SR41–SR47 |
| Suites green, checklists walked | every gate |
