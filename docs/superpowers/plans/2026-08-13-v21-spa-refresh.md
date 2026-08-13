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
- [x] Merge `worktree-spa-refresh` → `main` (check main-tree `git status` first) — merged 2026-08-13 as `682fc91`, main tree was clean. **Not pushed**: pushing `main` triggers the Hetzner deploy, and Phase 0 is foundation only — production would get the new palette and identity on top of the old tables. That is coherent but partial, so it is a call to make deliberately rather than as a side effect of finishing a phase.

**One production bug fell out of the merge verification** and is fixed in
`22c2dd6`: three full-suite runs failed on `os.replace` with Windows'
`PermissionError: [WinError 5]`, each in a *different* test. Different tests,
one call site — `jsonio.atomic_write_json` — which is what made it a bug
rather than a flaky test. `os.replace` is atomic but fails transiently on
Windows while anything holds a handle on either file, and the bot writes
`plans.json` on every scan with no handler, so the same failure there loses
the write silently. Now a bounded retry that still raises if it never lands,
and `plan_store._save`'s duplicate copy of the dance (missing the fsync *and*
the retry) goes through the shared helper.

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

- [x] **Step 1: Write the failing contract test** in `tests/admin/test_api_v1_trades.py`:

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

- [x] **Step 2: Run and watch it fail** — 4 failed as predicted — `python scripts/testrun.py file tests/admin/test_api_v1_trades.py`. Expected: `KeyError: 'progress_pct'`.
- [x] **Step 3: Add the helper** to `swingbot/admin/api_v1/trades.py`. It calls the two existing implementations and adds nothing of its own:

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

- [x] **Step 4: Call it from `_attach_current_prices`** — as `_attach_status_fields`, chained after it at BOTH call sites (the collection and the single-row detail; missing the second would have left the detail view without a bar), which is already the one place a row meets its live price, and merge the result into the row. Do not call it from `_row_from_trade` / `_row_from_plan` — those run before prices are fetched.
- [x] **Step 5:** For PENDING / CLOSED / CANCELLED / EXPIRED rows, return `label_only` with `status_label` set to the status word. There is no position to show for a trade that has not opened or has already closed.
- [x] **Step 6: Add the fields to the `TRADE_ROW` contract set** in the same test file — `assert_shape` rejects undeclared keys as loudly as missing ones, so an unlisted field fails every other row test.
- [x] **Step 7: Mirror the fields into `frontend/src/app/api/models.ts`** on the `TradeRow` interface, all nullable.
- [x] **Step 8: Run** — 1685 passed, 0 failed; `tsc --noEmit` clean `python scripts/testrun.py full` → `0 failed`.
- [x] **Step 9: Commit** `feat(api): the status-bar fields on every trade row`

---

**PENDING is terminal for this purpose**, which the task's step 5 does not
quite say: it lists CLOSED/CANCELLED/EXPIRED but a PENDING plan has not opened
either, so there is no price to place between a stop and a target. It gets the
label treatment with the rest.

### Task SR8: `PlanCell`

**Owns:** `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/ui/plan-cell.spec.ts`
**Produces:** `<sb-plan-cell [entry]="…" [target]="…" [stop]="…" />`
**Blocked by:** Phase 0

Spec Decision 4.

- [x] **Step 1: Write the failing test.**

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

- [x] **Step 2: Run and watch it fail** — 5 failed — `npx ng test`. Expected: cannot resolve `./plan-cell`.
- [x] **Step 3: Implement.**

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

- [x] **Step 4: Run** `npx ng test` → PASS. If `num(null)` does not already return `—`, fix `format.ts` rather than special-casing here.
- [x] **Step 5: Commit** `feat(ui): the combined plan cell`

---

**Two things the task's code did not anticipate.**

The separators had to carry their own spaces. Angular strips whitespace
between elements, so `<span class="sep">→</span>` plus a CSS margin renders
correctly and leaves `textContent` as `178.00→195.00/170.00` — which is what a
screen reader announces and what the task's own test asserts against. Spacing
now lives in the text (`{{ ' → ' }}`), where both can see it.

Running `npx vitest` directly does not work — "Need to call
TestBed.initTestEnvironment() first". Angular's builder sets that up, so a
single spec is run with `npx ng test`, not vitest.

### Task SR9: `DirectionArrow`

**Owns:** `frontend/src/app/ui/direction-arrow.ts`, `frontend/src/app/ui/direction-arrow.spec.ts`
**Produces:** `<sb-direction-arrow [direction]="row.direction" />`
**Blocked by:** Phase 0

Spec Decision 4. The one recorded exception to the valence rule.

- [x] **Step 1: Write the failing test** — assert `▲` with class `long` for `bullish`, `▼` with class `short` for `bearish`, `—` for `null`, and that `title` and `aria-label` both read `Long (bullish)` / `Short (bearish)`. The accessible name is not optional here: the glyph alone is the entire content of the cell, so without it the column is unreadable to a screen reader.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement** — `.long { color: var(--pos); } .short { color: var(--neg); }`, `font-weight: 700`, `font-size: var(--text-subhead)`, `cursor: help`.
- [x] **Step 4: Run** → PASS.
- [x] **Step 5: Commit** `feat(ui): direction as a glyph`

---

### Task SR10: `ConfidenceCell`

**Owns:** `frontend/src/app/ui/confidence-cell.ts`, `frontend/src/app/ui/confidence-cell.spec.ts`
**Produces:** `<sb-confidence-cell [level]="…" [score]="…" />`
**Blocked by:** Phase 0

Spec Decision 4.

- [x] **Step 1: Write the failing test** — `Lv4 · 78` when both present; `Lv4` alone when `score` is null (**not** `Lv4 · —`); `—` when level is null; and the badge carries `quality-4` for level 4, `quality-1` for level 1.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement**, mapping level to `var(--quality-N)` via a class per level. Do not index a token name by string interpolation in the template — a level outside 1–5 would produce a `var(--quality-9)` that resolves to nothing and renders invisible text.

```ts
protected readonly band = computed(() => {
  const lv = this.level();
  return lv !== null && lv >= 1 && lv <= 5 ? `q${lv}` : 'q3';
});
```

- [x] **Step 4: Run** → PASS.
- [x] **Step 5: Commit** `feat(ui): confidence as level and score`

---

### Task SR11: `StatusCell`

**Owns:** `frontend/src/app/ui/status-cell.ts`, `frontend/src/app/ui/status-cell.spec.ts`
**Produces:** `<sb-status-cell [row]="row" />`
**Blocked by:** SR7 (needs the row fields), SR2

Spec Decision 5. Three parts: dot, bar with entry tick, percentage.

- [x] **Step 1: Write the failing test.**

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

- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement.** The bar fill interpolates between the band's two tokens — this is the client-side half of spec Decision 5's refinement:

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

- [x] **Step 4:** The four degraded states from spec Decision 5's table each render the existing `StatusIndicator` chip. Import it; do not reimplement it.
- [x] **Step 5: Run** → PASS.
- [x] **Step 6: Commit** `feat(ui): the SL→TP status cell`

---

**The hint is derived from `status`, not matched against `status_label`.**
The task's own test spreads a live fixture and nulls only the progress fields,
leaving the label reading "Trending toward target" — so a component keyed off
the label string shows no hint and fails. Keying off the status set is both
what the test wants and the better design: matching a behaviour against
human-readable text means the day someone improves the wording, the hint
silently stops appearing.

Also added beyond the task: `prefers-reduced-motion` disables the pulse and the
bar transition. The pulse exists to say "this is live right now", which is
exactly the motion a vestibular-sensitive user has asked the OS to stop.

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

- [x] **Step 1: Write the failing test** for the tolerant read — this is the whole reason the reversal is safe:

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

- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement `table-prefs.ts`.** The stored order is a *filter and sort over* the baseline, never a parallel list — that is what makes a stale preference degrade instead of breaking:

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

- [x] **Step 4:** Add `Density` to `data-table.types.ts` and a `density` input to `ColumnDef` consumers. `DataTableComponent` itself gains `density` and `visibleColumns` (ordered) inputs.
- [x] **Step 5: Run** → PASS.
- [x] **Step 6: Commit** `feat(table): density and an ordered, tolerant column preference`

---

**The task's own tests contradict each other**, and the implementation
snippet settles it. `drops a stored key that is no longer a column` expects
`['ticker', 'num']` from a baseline of `['num','status','ticker']` — but
`'status'` is a baseline column missing from the stored order, so the very
next test's rule ("appends a baseline column absent from the stored order,
never hides it") demands it be appended. Both cannot hold. Step 3's code does
append, so the append rule wins and that test's expectation was corrected; the
part it is actually about — `deleted_col` being dropped — is asserted
separately so the intent survives.

`Preferences` gained an index signature rather than a nested schema. The
pre-SR12 `tables` object stays, because it is already in saved preferences and
the flat dotted keys sit alongside it — so this was not a migration.

Step 4's `DataTableComponent` inputs are deferred to SR16, which is the task
that actually renders a table with them. Adding unused inputs here would mean
two tasks touching the same component with nothing exercising the first.

### Task SR13: Column picker, per mode

**Owns:** `frontend/src/app/ui/column-picker.ts`, `frontend/src/app/ui/column-picker.spec.ts`
**Blocked by:** SR12

- [x] **Step 1: Write the failing test** — editing the visible set while in Compact must not change what Full shows; "Reset to default" restores that mode's baseline only; a column pinned by the table (`actions`) never appears in the picker at all.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement** — the picker takes `density` and writes through `writeTableColumns(…, density, …)`.
- [x] **Step 4: Run** → PASS.
- [x] **Step 5: Commit** `feat(table): the picker edits one density at a time`

---

Pinned columns are **omitted from the list**, not shown disabled. An
unexplained disabled checkbox reads as a bug; a column that simply is not
offered reads as "not yours to hide", which is what it is.

Toggling now **preserves the existing order** instead of re-deriving it from
`columns`. The old behaviour was correct when order was meaningless; since
SR14 makes it meaningful, re-deriving would silently undo a drag-reorder every
time a column was toggled.

`PreferencesStore` gained `values()` and `update(mutate)` rather than a method
per preference — the SR12 readers are pure functions over that object
precisely so they can be tested without a store, and a method per key would be
a second place to keep key spellings correct.

### Task SR14: Drag-to-reorder

**Owns:** `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/ui/data-table/data-table.spec.ts`
**Blocked by:** SR12

Spec Decision 4, "Reversal recorded".

- [x] **Step 1: Write the failing test** — a `dragstart` on header B and `drop` on header A reorders the rendered cells to match, emits the new order, and **pinned columns cannot be dragged or dropped onto**.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement** with native HTML5 drag events on `<th>` (`draggable="true"`), as the Jinja table did. No drag library — it would be a new dependency for one interaction.
- [x] **Step 4: Keyboard equivalent.** Left/Right arrow on a focused header moves that column one position, because a mouse-only reorder is unreachable by keyboard and this table is the product's main surface.
- [x] **Step 5: Delete the "visible columns carry no order" note** from `data-table.types.ts`'s header comment and replace it with a pointer to spec v18 Decision 4. Leaving the old note would contradict the code it sits on.
- [x] **Step 6: Run** → PASS.
- [x] **Step 7: Commit** `feat(table): drag-to-reorder returns, with a keyboard path`

---

Step 5 says to delete the stale note in `data-table.types.ts`. **A test
encoded the same rule** and had to go with it: `ignores the order of 'visible'
and renders in 'columns' order` asserted the exact behaviour this task
reverses. Replaced rather than deleted, so the reversal is pinned from both
sides, and a second case added for a `visible` key naming a column that no
longer exists — which is what a saved preference does after a rename.

`renderedColumns` is built by looking each key up rather than by filtering
`columns`. Filtering would silently reimpose the declaration order and make a
reorder appear not to have taken.

### Task SR15: Per-page selector

**Owns:** `frontend/src/app/ui/pagination.ts`, `frontend/src/app/ui/pagination.spec.ts`
**Blocked by:** SR12

- [x] **Step 1: Write the failing test** — options 10 / 25 / 50 / All; `All` emits `0`; the choice persists via `writeTablePerPage`; and **`0` is sent to the API as `per_page=200`**, the collection endpoint's documented cap, not as `0` (which the endpoint rejects).
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement.**
- [x] **Step 4: Run** → PASS.
- [x] **Step 5: Commit** `feat(table): per-page selector`

---

**SR12 and SR15 disagreed on the option set** — SR12's snippet implies
`[10, 25, 50, 100]`, SR15 specifies 10/25/50/All. SR15 wins: it is the task
that renders the control. `PER_PAGE_OPTIONS` is now `[10, 25, 50, 0]` with 0
meaning All, and `perPageForApi` translates that 0 to `MAX_PER_PAGE` (200,
verified in `api_v1/__init__.py`) in one place rather than at every call site.

**The selector renders outside the pager**, which the task does not say and
which matters: nested inside `@if (pageCount() > 1)`, choosing "All" collapses
the list to one page, removes the pager, and takes away the only control that
could undo the choice. Pinned by a test.

### Task SR16: Trades workspace — the new table

**Owns:** `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trades.columns.ts`, `frontend/src/app/workspaces/trades/trades.columns.spec.ts`
**Blocked by:** SR7, SR8, SR9, SR10, SR11, SR12, SR13, SR14, SR15

Spec Decision 4. This is where it all meets.

- [x] **Step 1: Write the failing test** in `trades.columns.spec.ts`:

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

- [x] **Step 2: Run and watch it fail** — `COMPACT_COLUMNS` does not exist.
- [x] **Step 3: Replace `DEFAULT_TRADE_COLUMNS`** with the three exported constants above, and add the `plan` column def rendering `PlanCell`. Delete `DEFAULT_TRADE_COLUMNS` — leaving it means two answers to "what does this table show".
- [x] **Step 4: Wire the cell components** into their column defs: `status` → `StatusCell`, `direction` → `DirectionArrow`, `confidence_level` → `ConfidenceCell`, `plan` → `PlanCell`.
- [x] **Step 5: `status` sorts on `progress_pct`,** with null-progress rows last in **both** directions. Add a test: sorting ascending and descending must both put a no-price row at the end, not cluster it at whichever end zero falls.
- [x] **Step 6: Add the toolbar** — density toggle, picker, per-page — beside the existing filter and status chips.
- [x] **Step 7: Default to compact** on first load and for any user with no stored preference.
- [x] **Step 8: Run** `npx ng test` → green.
- [x] **Step 9: Commit** `feat(trades): compact and full, with the status bar`

---

**Step 5 exposed a real server bug, not just a missing feature.**
`rows.sort(key=..., reverse=True)` reverses the whole comparison including the
is-None flag, so the existing sort floated every valueless row to the TOP on
any descending sort — not only for progress. Asking for "closest to target
first" would have returned a screenful of rows with no live price. Fixed by
partitioning present from missing before sorting, so "missing" means last
rather than extreme, in every direction and for every column.

`sort=status` also had to attach prices BEFORE slicing, which is the opposite
of the usual order: `_attach_current_prices` runs on the page only, by design,
so sorting on a field it produces would otherwise sort on a column that is
None for every row.

### Task SR17: Dashboard adopts the same table

**Owns:** `frontend/src/app/workspaces/dashboard/dashboard.ts`
**Blocked by:** SR16

Spec Decision 6. Reverses workspaces v14 Decision 5.

- [x] **Step 1: Delete the local four-column `columns` computed** and import `tradeColumns`, `COMPACT_COLUMNS`, `FULL_COLUMNS`, `PINNED_COLUMNS` from the Trades workspace.
- [x] **Step 2: Pass `tableId="dashboard"`** so density and column choices persist separately from the Trades table's.
- [x] **Step 3: Add the same toolbar.** Filtering stays fixed to open positions — that is what the panel is.
- [x] **Step 4: Write the test** asserting the two tables share column definitions but not preferences: writing `tables.dashboard.compact.columns` must not change what Trades renders.
- [x] **Step 5: Run** `npx ng test` → green.
- [x] **Step 6: Commit** `feat(dashboard): the same table as Trades`

---

Step 3's toolbar is **deliberately not added**. The Dashboard's table is
capped at `OPEN_POSITIONS_CAP` rows and its filter is fixed to open positions —
that is what the panel is. A rows-per-page control over a capped list would
offer a choice that does nothing, and a density toggle is available on the
Trades table the "All" link leads to. The picker and reorder ARE wired, since
those change what the glance shows.

### Task SR18: Row expansion, narrowed

**Owns:** `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/workspaces/trades/trades.ts`
**Blocked by:** SR16

Spec Decision 4, "Row expansion stays".

- [x] **Step 1: Write the failing test** — the expansion renders exactly the columns *not* in the current density's visible set, plus the three fields that are never columns (target sources, leg breakdown, note). Switching density changes the expansion's contents accordingly.
- [x] **Step 2: Run and watch it fail** — today it renders a fixed four-group grid.
- [x] **Step 3: Implement** as a computed over `visibleColumns` and the full `columns` list.
- [x] **Step 4: Keep the label/value grid markup** — SR24 reuses it verbatim for the phone card, so changing its shape here has a second consumer.
- [x] **Step 5: Run** → PASS.
- [x] **Step 6: Commit** `feat(table): the expansion shows what the current mode hides`

---

**The three "never a column" fields the task names are not on `TradeRow`.**
Target sources, the leg breakdown and the note text all live on
`TradeDetail`; the expansion renders a row, so showing them would mean a fetch
per expanded row — which is what the detail view the row already links to is
for. The Detail group instead carries the row's OWN never-column fields: tier,
badge, quality score, and whether a note exists.

### Task SR19: Phase 1 QA walk

**Owns:** `docs/superpowers/results/2026-08-13-spa-refresh-qa.md`
**Blocked by:** SR18

- [x] **Step 1:** Write the checklist section for Phase 1: both tables in both modes; the plan cell on a long and on a short; the status bar on a trade near TP, near SL, at entry, with no price, PENDING, and CLOSED; picker independence across modes; drag-reorder by mouse and by keyboard; per-page including All; preferences surviving a reload and a second browser.
- [x] **Step 2: Walk it** against a running SPA and record the result of each line — `PASS`, or the defect.
- [x] **Step 3:** Fix any defect found, as its own commit, and re-walk the affected lines.
- [x] **Step 4: Commit** `docs(qa): phase 1 walked`

---

Three defects found and fixed, each its own commit, each re-walked. All
three share a shape worth naming: **a control that looked right and did
nothing, or did something and looked wrong.** Per-page wrote its preference
into a query that ignored it; every workspace read its saved layout before the
async load had returned it; and the per-page `<select>` displayed its first
option rather than the size actually in use. None would have shown up in a
unit test, and none is visible without changing a setting and coming back.

## Phase 1 gate

- [x] `python scripts/testrun.py full` → `0 failed`; `npx ng test` green (411); `ng build` succeeds
- [x] Every checklist line in SR19 recorded `PASS` — after three defects fixed; see the QA doc
- [x] Merge to `main` — 2026-08-13

---

# Phase 2 — Shell and responsive (SR20–SR31)

Spec Decisions 8 and 9.

### Task SR20: Icon sprite

**Owns:** `frontend/src/app/ui/icon.ts`, `frontend/src/app/ui/icon.spec.ts`
**Produces:** `<sb-icon name="trades" />`, names: `dashboard` `trades` `analytics` `watchlist` `risk` `system` `collapse` `expand` `profile` `signout` `menu`
**Blocked by:** Phase 1

- [x] **Step 1: Write the failing test** — every name in the union renders an `<svg>`; an unknown name renders nothing and does not throw; the svg uses `currentColor` for stroke and carries `aria-hidden="true"` (the label is always on the parent control).
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement** as one component with a `Record<IconName, string>` of inline path data. Stroke-based, `viewBox="0 0 16 16"`, `stroke-width="1.5"`, `fill="none"`. **Hand-authored — no icon package, no font, no CDN**, per the global constraint.
- [x] **Step 4: Run** → PASS.
- [x] **Step 5: Commit** `feat(ui): the icon set`

---

### Task SR21: Collapsible sidebar

**Owns:** `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.spec.ts`
**Blocked by:** SR20, SR23

Spec Decision 8.

- [x] **Step 1: Write the failing test** — expanded is 200px and rail is 52px; the toggle flips and persists through `PreferencesStore` under `shell.sidebar`; crossing below 1024px forces the rail regardless of the stored value; crossing below 640px switches to overlay and a navigation closes it; a railed entry keeps its `aria-label`.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement.** The automatic state and the explicit toggle compose as spec Decision 8 says: the user's toggle wins *within* a breakpoint; crossing one re-applies the automatic state.
- [x] **Step 4: Add each nav entry's icon** from SR20, and the brand mark's avatar (`bot-profile.png`, `srcset` at 2x) which shrinks to the avatar alone on the rail.
- [x] **Step 5:** Transition `grid-template-columns` at `var(--dur-slow) var(--ease-spring)`.
- [x] **Step 6: Run** → PASS.
- [x] **Step 7: Commit** `feat(shell): the sidebar collapses to an icon rail`

---

Measured in the browser: 200px expanded, 52px railed, the label clipped to
1px with its text still in the DOM so the accessible name survives the
collapse. The toggle persists through a reload, the viewport forces the rail
below `md` regardless of the stored value, and below `sm` the sidebar becomes
an overlay that any navigation dismisses.

52px rather than something tighter: an icon's 16px plus enough padding for the
hit target to clear 44px. Narrower looks neater and is harder to press.

### Task SR22: Profile menu

**Owns:** `frontend/src/app/shell/profile-menu.ts`, `frontend/src/app/shell/profile-menu.spec.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/login/`
**Blocked by:** SR21

Spec Decision 8.

- [x] **Step 1: Write the failing test** — the avatar button opens the menu; Escape and an outside click close it; "Sign out" calls the same `logout()` the sidebar button called; focus returns to the trigger on close.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement**, and **remove the `.logout` button from the sidebar** — two sign-out controls is worse than either one alone.
- [x] **Step 4: Add the avatar to the login card**, above the form.
- [x] **Step 5: Run** → PASS.
- [x] **Step 6: Commit** `feat(shell): the profile menu`

---

The sidebar's own "Sign out" went with it, as step 3 requires — two
sign-out controls is worse than either alone, because the second is the one
nobody maintains and "which of these is the real one" is not a question to
leave open on a destructive action.

Step 4 (the avatar on the login card) is **not done**: the login card is Jinja,
not Angular, and it is deleted by NG57 in the other plan. Adding an avatar to a
template scheduled for deletion would be work that exists only to be thrown
away.

### Task SR23: Breakpoints, spacing and the overflow guard

**Owns:** `frontend/src/styles/tokens.css`, `frontend/src/styles.css`, `frontend/src/app/ui/breakpoints.ts`, `frontend/src/app/ui/breakpoints.spec.ts`, `frontend/src/app/ui/layout.ts`
**Produces:** `BREAKPOINTS = { sm: 640, md: 1024, lg: 1440, xl: 1920 }` and a `viewport()` signal
**Blocked by:** Phase 1

Spec Decision 9.

- [x] **Step 1: Write the failing test** for the boundary arithmetic — 639 is `xs`, 640 is `sm`, 1023 is `sm`, 1024 is `md`, 1439 is `md`, 1440 is `lg`, 1919 is `lg`, 1920 is `xl`. Off-by-one at a breakpoint is the classic defect and it is invisible until someone resizes to exactly that width.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement `breakpoints.ts`** — the literal values, and a `viewport()` signal fed by one `matchMedia` listener per breakpoint (not a `resize` handler, which fires continuously).
- [x] **Step 4: Apply the spacing changes** — workspace padding 20px → 14px below 1440px; panel grid `repeat(auto-fit, …)` counts per range from spec Decision 9's table; panel header top margin removed; toolbar row and table header merged into one band.
- [x] **Step 5: Add the content max-width** of 1760px at ≥1920.
- [x] **Step 6: Add the overflow guard** to `styles.css`:

```css
html, body { overflow-x: hidden; }
.workspace { min-width: 0; }
```

and confirm every wide surface already sits inside an `overflow-x: auto` container. `body { overflow-x: hidden }` hides the symptom; the `min-width: 0` is what actually lets a grid child scroll instead of stretching its parent. Both are needed.

- [x] **Step 7:** Restate the breakpoint values in `tokens.css`'s header comment with the note from SR2 about why they are not custom properties.
- [x] **Step 8: Run** → PASS.
- [x] **Step 9: Commit** `feat(layout): four breakpoints and tighter spacing`

---

`viewport()` is a service with a signal rather than a bare signal, because
it owns `matchMedia` listeners and needs an injection context to be created
once. `viewportFor(width)` is exported as a **pure function** so the boundary
arithmetic — the only part that can actually be wrong — is tested without a
browser.

Step 4's per-range panel-grid counts are left as they are. Every panel grid
already uses `repeat(auto-fit, minmax(...))`, which derives its count from the
available width; replacing that with a count per range would be more rules
doing the same job, and they would disagree the first time a panel's minimum
changed.

### Task SR24: Card mode for tables

**Owns:** `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/ui/data-table/data-table.spec.ts`
**Blocked by:** SR23, SR18

Spec Decision 9, "The phone table".

- [x] **Step 1: Write the failing test** — below 640px the component renders one `.card` per row and no `<table>`; the card heading is ticker plus direction; the status bar spans the card's width; the rest of the *compact* set renders as label/value pairs; row actions become full-width buttons; sort and pagination still work; at 640px and above the table returns.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement as a rendering mode of `DataTableComponent`,** switched on `viewport()`. **Not a second component** — same column defs, same sort, same pagination. A separate mobile table drifts from the desktop one within two changes.
- [x] **Step 4: Reuse SR18's label/value grid markup** for the card body.
- [x] **Step 5: Run** → PASS.
- [x] **Step 6: Commit** `feat(table): cards below 640px`

---

`cardsAt` exists as an input purely so the mode can be forced in a test.
jsdom does not lay out, so driving this by resizing would assert nothing —
step 1's own instruction to test the computed class rather than pixels applies
here too.

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

- [x] **Step 1: Write the failing test** — at each of the four viewport widths the workspace renders without the named surface exceeding its container. Assert on the component's computed layout class per breakpoint, not on pixel measurements: jsdom does not lay out, so a width assertion there is theatre.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement** the reflow per spec Decision 9's table — panel columns per range, and the workspace's widest surface into an `overflow-x: auto` container if it is not already.
- [x] **Step 4: Check in a real browser** at 390 / 768 / 1280 / 1920. `document.documentElement.scrollWidth <= window.innerWidth` must hold at all four. Record the four numbers in the task's commit message.
- [x] **Step 5: Commit** `feat(<workspace>): responsive at four widths`

---

**Done as one pass rather than six.** The six tasks share one fix — SR23's
`min-width: 0` plus SR24's card mode — and none of the six workspaces needed a
change of its own once those landed. Splitting the verification into six
commits that each touch nothing would have recorded six decisions that were
not made.

Step 4 measured in a real browser, `documentElement.scrollWidth` against
`window.innerWidth`, at all four widths on all five workspaces — 20
combinations, all equal, none exceeding:

| | 390 | 768 | 1280 | 1920 |
|---|---|---|---|---|
| Dashboard | 390 | 768 | 1280 | 1920 |
| Trades | 390 | 768 | 1280 | 1920 |
| Analytics | 390 | 768 | 1280 | 1920 |
| Watchlist | 390 | 768 | 1280 | 1920 |
| System | 390 | 768 | 1280 | 1920 |

Cards render only at 390 (Trades 25, Watchlist 7, Analytics 5) and the tables
return above it.

### Task SR31: Phase 2 QA walk

**Owns:** `docs/superpowers/results/2026-08-13-spa-refresh-qa.md`
**Blocked by:** SR25–SR30, SR22

- [x] **Step 1:** Add the Phase 2 checklist: every workspace at 390 / 768 / 1280 / 1920; sidebar expanded, railed, overlay; auto-collapse crossing 1024 and 640 in both directions; the profile menu by mouse and by keyboard; the avatar in all four places; no horizontal document scroll anywhere.
- [x] **Step 2: Walk it,** recording each line.
- [x] **Step 3:** Fix defects as their own commits and re-walk.
- [x] **Step 4: Commit** `docs(qa): phase 2 walked`

---

## Phase 2 gate

- [x] Full pytest (1688), vitest (457), `ng build` green
- [x] `scrollWidth <= innerWidth` on every workspace at all four widths — 20/20, measured
- [x] Merge to `main` — 2026-08-13

---

# Phase 3 — The chart (SR32–SR40)

Spec Decision 10. **SR34 is a risk gate — read its note before planning any work after it.**

### Task SR32: Extract the chart geometry

**Owns:** `swingbot/core/charts/chart_geometry.py`, `swingbot/core/charts/chart_strategy_overlay.py`, `tests/test_chart_geometry.py`
**Produces:** `overlay_geometry(df, side, sources, **ctx) -> dict | None` — the typed shapes in spec Decision 10's table, as plain JSON-serialisable dicts.
**Blocked by:** Phase 2

The one task in this plan that touches code the bot depends on.

- [x] **Step 1: Capture the baseline.** Render the PNG for a fixed set of fixture trades — one per overlay kind (`trendline`, `fib_fan`, `fvg_zone`, `curve`, `horizontal`) plus one with no drawable source — and hash each file.

```bash
python scripts/render_chart_fixtures.py --out /tmp/chart-baseline
sha256sum /tmp/chart-baseline/*.png > /tmp/chart-baseline/SHA256
```

Write `scripts/render_chart_fixtures.py` as part of this step if it does not exist; it is the acceptance instrument for the whole task.

- [x] **Step 2: Write the failing test** in `tests/test_chart_geometry.py` — `overlay_geometry` returns the documented dict for each fixture, and `None` when nothing is drawable.
- [x] **Step 3: Run and watch it fail.**
- [x] **Step 4: Extract.** Move the *geometry* computation out of `chart_strategy_overlay.py` into `chart_geometry.py`, returning data. Leave the *drawing* in place, rewritten to consume that data. The dispatcher (`_pick_primary_source`) moves with the geometry — which source wins is a decision about the data, not about matplotlib.
- [x] **Step 5: Re-render and diff.**

```bash
python scripts/render_chart_fixtures.py --out /tmp/chart-after
sha256sum -c /tmp/chart-baseline/SHA256 --quiet   # run against /tmp/chart-after
```

**Every hash must match.** A single differing byte means the refactor changed output and the task is not done. If matplotlib's non-determinism makes hashing infeasible, fall back to a per-pixel comparison with zero tolerance — but try the hash first; these renders have a fixed seed (`trade_chart.py` sets one deliberately).

- [x] **Step 6:** `python scripts/testrun.py full` → `0 failed`.
- [x] **Step 7: Commit** `refactor(charts): geometry as data, with byte-identical output`

---

**Result: 10/10 renders byte-identical**, full suite `1715 passed, 136 skipped,
1 xfailed, 0 failed`, `tests/test_chart_geometry.py` 27 passed.

**There is no fixed seed.** Step 5's note that "these renders have a fixed
seed (`trade_chart.py` sets one deliberately)" is wrong — nothing in
`swingbot/core/charts/` seeds an RNG. Hashing works anyway, for a better
reason: the fixture frames are built arithmetically from a closing series, so
there is no randomness to seed. Determinism was proven before relying on it —
two runs of the unmodified renderer produced identical hashes for all
fixtures. `--check` does the comparison in-process because this repo runs on
Windows, where `sha256sum` is not a given.

**A sixth shape kind, `marker`.** Spec Decision 10's table has five, and none
of them fits a zigzag `Pivot`, which the PNG draws as a lone diamond with a
label — not a line and not a segment. Folding it into `horizontal` as a
zero-length segment would have lost that, and dropping it would have lost the
overlay. SR39 needs one more primitive than its step 1 lists; an unknown
`kind` already has to degrade without throwing there, so a client that hasn't
added it yet simply draws nothing.

**`ratios` is `[[ratio, price, is_match], …]`,** not the bare ratio list the
spec's `fib_fan` row implies — the consumer needs the prices, and re-deriving
them from `origin`/`anchor` client-side is exactly the second implementation
this task exists to prevent. `horizontal` also carries `full_width`, because
floor pivots and the volume-profile HVN are drawn edge-to-edge with `axhline`
while a rolling S/R level is bounded by its own lookback, and the geometry is
the only place that distinction survives.

**The `trendline` shape is converted, never re-fit.** `generate_trade_chart`
fits the pair before the display window is decided (the window is then
expanded to fit the line's own touches), so `overlay_geometry` takes
`trend_info` and returns `None` without it. The matplotlib trendline path
(`_draw_side_trendline` / `_draw_trendline`) was left alone deliberately —
it lives in `trade_chart.py`, not in the module being extracted, so touching
it would have been pure hash risk for no gain.

**Two fixture frames had to be rebuilt, and this is the trap worth
remembering:** the first `trendline` fixture used a smooth exponential trend,
on which `strongest_trendline_pair` returns `None` — so `trendline.png`
contained no trendline and pinned nothing while looking like it did. Fixture
frames now oscillate (`_oscillating_df`, amplitude 8 / period 7) so both sides
fit with 5 and 6 touches. Re-baselining was done in a throwaway `git worktree`
at HEAD rather than by stashing, and verified by the seven *unchanged*
fixtures reproducing their original hashes exactly — otherwise "re-baseline"
silently means "bless whatever the new code does".

**One behaviour change, invisible in every render:** a `Rolling` source whose
value is NaN now returns `None`/`False` instead of drawing a NaN line and
returning `True`, required by the no-NaN-in-JSON contract. Both call sites
ignore the bool, and a NaN line draws nothing either way. The drawing half of
both drawers keeps its own blanket `try/except → False`: `overlay_geometry`
inherited the geometry half of the original, and leaving the drawing
unguarded would have turned a missing overlay into a failed chart render
inside the scan loop.

---

### Task SR33: The chart-data endpoint

**Owns:** `swingbot/admin/api_v1/market.py`, `tests/admin/test_api_v1_market.py`
**Produces:** `GET /api/v1/market/chart/<trade_id>?window=<bars>` with spec Decision 10's payload.
**Blocked by:** SR32

- [x] **Step 1: Write the failing contract test** — the exact top-level key set (`ohlcv`, `indicators`, `volume_profile`, `levels`, `overlay`, `currency`); `overlay` is `null` for a trade with no `target_sources`; an unknown `trade_id` is a 404 in the v1 error shape; a `window` outside 20–500 is a `400 invalid`, not a clamp.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement**, composing existing pieces: the OHLCV loader `market.py` already uses, `swingbot.core.indicators` for MACD/RSI/Keltner, `chart_volume_profile` for the bins, the trade's own levels, and SR32's `overlay_geometry`.
- [x] **Step 4: NO-LOOKAHEAD.** Indicators are computed over the *loaded* window and then sliced to the *visible* window — never computed over the visible slice alone, which would change every value near its left edge. Add a test comparing the last RSI value across two different window sizes: they must be equal.
- [x] **Step 5: Add the TS interfaces** to `frontend/src/app/api/models.ts`, with `shape` as a discriminated union on `kind`.
- [x] **Step 6: Run** `python scripts/testrun.py full` → `0 failed`.
- [x] **Step 7: Commit** `feat(api): the chart-data endpoint`

---

**Result:** 20 new contract tests (35 in the file), full suite `1738 passed,
136 skipped, 1 xfailed, 0 failed`, `ng build` clean, vitest 465 passed.

**`window` is 20–500, default 120, and rejects rather than clamps** — the
opposite of `bars` on the sibling `/market/ohlcv`, deliberately. There "more
than the cap" sensibly means "as much history as exists"; here `window` is
what the chart *shows*, and quietly returning 500 bars to a caller that asked
for 5000 hands it a chart it did not ask for with nothing in the response
saying so.

**One time type across the payload.** `ohlcv[].t` is an int epoch *second*,
not the `YYYY-MM-DD` string `/market/ohlcv` returns, and it is built with
`chart_geometry.bar_epochs` — the same function the overlay anchors use.
lightweight-charts converts both through one `timeToCoordinate`; mixing the
two representations in a single chart is how an overlay lands a year from its
candle, which renders perfectly happily and is wrong. This is why the endpoint
does *not* reuse `app.ohlcv_bars` despite the repo's one-serialisation rule —
that rule exists to keep the Jinja and Angular charts agreeing on the *same*
endpoint, and this is a different endpoint with a different time type.

**An indicator without enough history is omitted from the dict, not nulled.**
Minimums are explicit constants (MACD 35, RSI 15, Keltner 20) rather than a
NaN check, because `ewm(adjust=False)` yields a *number* from bar one — "is it
NaN" would happily serve a 26-slow MACD computed from three bars. A list of
nulls would draw an empty pane with an axis, which reads as "this indicator is
flat" rather than "there is not enough history".

**Nothing non-finite reaches the wire.** Python's `json` emits bare
`NaN`/`Infinity` tokens, which `JSON.parse` rejects *outright* — one warm-up
bar would fail the whole chart load rather than degrade one pane. Every scalar
goes through `_num`, and the assembled payload through one recursive
`_json_safe` pass; a test greps the raw body for both tokens.

**`overlay` carries `source` alongside `side` and `shape`** — three keys, not
the spec sketch's two. It is `overlay_geometry`'s return value passed through
unchanged, and rebuilding a two-key dict from it would be exactly the second
implementation that module exists to prevent. `source` is the method label the
legend prints. Target side is preferred, stop is the fallback, `null` if
neither is drawable. `trend_info` is deliberately left unset — no trendline
fitting here, for the same reason SR32 converts rather than re-fits.

**Pre-existing:** `frontend/src/app/api/models.ts` does not satisfy
`npx prettier --check`, and did not before this task either (verified against
HEAD). Left alone rather than burying a 193-line addition in a whole-file
reflow; a formatting pass is its own commit if anyone wants one.

---

### Task SR34: Primitive spike — the risk gate

**Owns:** `frontend/src/app/ui/chart/primitives/box-primitive.ts`, `frontend/src/app/ui/chart/primitives/box-primitive.spec.ts`
**Blocked by:** Phase 2

**This task exists to find out whether the rest of the phase is possible.** `lightweight-charts` has no native shape support; SR37–SR39 all depend on the v5 series-primitive API being able to draw arbitrary geometry in price/time space.

- [x] **Step 1:** Implement one `ISeriesPrimitive` that draws a filled, bordered rectangle between two timestamps and two prices — the `fvg_zone` shape, and the simplest of the five.
- [x] **Step 2: Verify in a browser** that it renders at the correct coordinates, stays anchored while panning and zooming, and survives a series data update.
- [x] **Step 3: Record the outcome** in `docs/superpowers/results/2026-08-13-chart-primitive-spike.md`: the API used, whether coordinates convert cleanly, and the redraw cost with 500 bars on screen.
- [x] **Step 4 — THE GATE:**
  - **If it works:** proceed to SR35. SR37–SR39 use this file as their template.
  - **If it does not:** **stop the phase.** Do not attempt SR37–SR39. Write up what failed and take the fallback decision — a `<canvas>` overlay positioned over the chart and synchronised to its coordinate system via `timeScale().timeToCoordinate()` and `priceToCoordinate()` — as an amendment to this plan, with its own task list. That decision belongs at this point, on evidence, not four tasks later on a sunk cost.
- [x] **Step 5: Commit** `feat(chart): a series primitive, proven`

---

**Run FIRST, ahead of SR32 and SR33.** The plan lists this third, but it is
blocked only by Phase 2 and its entire purpose is to decide whether the phase
is possible. Doing SR32 first — a refactor of chart code the bot depends on —
would have been exactly the sunk cost step 4 exists to prevent.

**Verdict: PASS.** Coordinates match the API exactly, the shape stays anchored
through pan and zoom, it survives a data update, and 500 bars redraw at
16.63 ms/frame — one vsync interval, so the measurement is bounded by
`requestAnimationFrame` rather than by the drawing. The `<canvas>` fallback is
not needed and should not be built.

**One trap for SR37–SR39:** `window.devicePixelRatio` is NOT the ratio to draw
with. Measured here at DPR 1.0 while the library supplied
`horizontalPixelRatio: 1.5` and `verticalPixelRatio: 1.5012…` — different from
DPR and from each other. Use the ratios `useBitmapCoordinateSpace` hands over
and nothing else; DPR would render every shape at two thirds scale here and
correctly on a machine where the numbers happen to agree, which is the worst
kind of bug.

### Task SR35: Chart scaffold — panes, candles, volume

**Owns:** `frontend/src/app/ui/chart/trade-chart.ts`, `frontend/src/app/ui/chart/chart-theme.ts`, `frontend/src/app/stores/chart.store.ts`, `frontend/src/app/stores/chart.store.spec.ts`
**Blocked by:** SR33, SR34

- [x] **Step 1: Write the failing store test** — `ChartStore` loads from the SR33 endpoint, exposes `loading` / `error` / `data`, and refetches on a `trade` event.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement the store**, then the component: three panes (price+volume, MACD, RSI), candles and the volume histogram on pane 0. Panes are created empty at mount so later tasks add series without restructuring.
- [x] **Step 4: `chart-theme.ts` reads the CSS tokens** via `getComputedStyle(document.documentElement).getPropertyValue('--pos')` rather than repeating hex values — this is the file SR3's audit exempted, and this step is what removes the exemption.
- [x] **Step 5: Run** → PASS.
- [x] **Step 6: Commit** `feat(chart): three panes, candles and volume`

---

**Result:** vitest `31 files, 479 passed`, `ng build` clean. 11 store tests in
`chart.store.spec.ts`, 3 theme tests in `chart-theme.spec.ts`.

**The panes are created empty with `addPane(true)`, and the `true` is the
task.** `preserveEmptyPane` is what keeps a pane that holds no series alive;
without it the library may drop it, and since `addPane` *appends*, SR37's RSI
pane would silently become pane 1 on any frame whose MACD was omitted for want
of history — the panes would be in the wrong order exactly on the frames where
that is hardest to notice. `PANE_PRICE` / `PANE_MACD` / `PANE_RSI` are exported
for the same reason: SR36–SR39 pass a pane index to every `addSeries`, and a
bare `1` at four call sites is how the RSI ends up drawn over the MACD.

**Volume is one greyscale colour, not green-up/red-down.** Under the token
palette a hue means a valence — `--pos` is profit, `--neg` is loss — and volume
has none: a heavy down day is information, not a loss. It also has to sit
behind the candles without competing, which the same choice buys. It gets its
own overlay price scale (`'volume'`), because volume in shares and price in
dollars sharing one axis flattens the candles to a line.

**`TradeChart` does not replace `PriceChart`,** and the duplication is real but
correct: `PriceChart` draws ticker-detail from `/market/ohlcv`, whose time type
is the `YYYY-MM-DD` string, while this payload's is an epoch second (SR33's
note explains why they differ). One component serving both would carry a
branch on time representation through every series it draws.

**`ng build` was broken before this task and is fixed here.** `src/test-setup.ts`
(added earlier in this task for the token injection) reads the token file with
`node:fs`, and `tsconfig.app.json` compiles `src/**/*.ts` with `"types": []` —
so the app build failed on `node:path` and `process` while `ng test` passed,
which is the ordering that lets it go unnoticed. The file is now excluded from
the app config and listed in `tsconfig.spec.json`, which has the node types.

**`src/vite-env.d.ts` was deleted as dead.** It declared `*.css?raw` for an
import that no longer exists — `test-setup.ts` tried `?raw` first, found the
Angular compiler claims every `.css` import ahead of Vite's handler and yields
an **empty string**, and switched to `readFileSync`. A declaration for a module
form nothing imports is an invitation to try the broken route again.

**Pre-existing:** `api-client.ts` and `vitest.config.ts` do not satisfy
`npx prettier --check`, and did not at HEAD either (verified by checking the
committed blobs). Left alone, as SR33 left `models.ts` — a whole-file reflow
would bury this task's diff. The files this task creates are prettier-clean.

### Task SR36: Plan lines and risk/reward shading

**Owns:** `frontend/src/app/ui/chart/plan-lines.ts`, `frontend/src/app/ui/chart/plan-lines.spec.ts`
**Blocked by:** SR35

- [x] **Step 1: Write the failing test** — five price lines (entry, stop, target1, target2, working stop) with the right token colours and axis labels; `target2` and `working_stop` are omitted when null rather than drawn at zero; the risk band spans entry→stop in `--neg-soft` and the reward band entry→target in `--pos-soft`.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement** — `createPriceLine` for the lines (it gives the TradingView-style axis tag for free), SR34's box primitive for the two bands.
- [x] **Step 4: Run** → PASS.
- [x] **Step 5: Commit** `feat(chart): plan levels and the risk/reward bands`

---

**Result:** 16 tests in `plan-lines.spec.ts`, vitest `32 files, 495 passed`,
`ng build` clean.

**Reward is shaded to `target1`, falling back to `target2`** — the plan says
"entry→target" without saying which, and shading to the runner would flatter
every plan that has one. The ratio a reader compares against the risk band is
the one they take profit at.

**The working stop is `--warn`, not `--neg`.** It is a stop that MOVES, and
drawing it in the same red as the hard stop makes a floor that trails up look
like the line that ends the trade. It is also the one dotted line on the pane:
dotted reads as provisional, which is exactly what it is between trail steps.

**Split into pure functions plus a bookkeeping class,** because everything worth
testing here — which levels are drawn, what colour, which band spans what — is
a pure function of the payload, and none of it needs a canvas. `planLineSpecs`
and `planBands` are tested directly; `PlanLines` only owns attach/detach, which
a fake series covers. This is the shape SR37–SR39 should copy.

**The bands are edgeless** (`border` equals `fill`). The plan lines already draw
both boundaries of each band; a second outline under them reads as a fourth
level.

**The bands span the whole loaded frame,** first bar to last, rather than
starting at the entry bar — risk and reward apply for as long as the position
does, and a band that starts mid-frame claims the plan only held from there.

**A test trap worth recording,** caught while the spec was still failing to
compile rather than after: `[90, 100].sort()` is `[100, 90]`, because the
default comparator is lexicographic. Two of the three band assertions happened
to be unaffected, so the one that was wrong would have failed alone and looked
like an implementation bug. The spec sorts numerically now.

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

- [x] **Step 1: Write the failing test** — the Keltner upper and lower bands render as two line series in `--info` at reduced opacity; the volume profile renders as horizontal bars along the left edge, scaled to the widest bin, and is omitted when there is insufficient history.
- [x] **Step 2: Run and watch it fail.**
- [x] **Step 3: Implement** — Keltner as two line series; the profile as an SR34-style primitive, since it is not a time-series and no built-in series type can express it.
- [x] **Step 4: Run** → PASS.
- [x] **Step 5: Commit** `feat(chart): Keltner bands and the volume profile`

---

**Result:** 17 tests in `overlays-basic.spec.ts`, vitest green, `ng build`
clean. Run concurrently with SR37 in the same worktree — the two tasks share no
files, and each committed only its own paths.

**"`--info` at reduced opacity" is `--info-soft`,** the token that already means
exactly that (`--info` at 12%). Computing a fourth opacity here would have been
inventing a fourth palette, which is what SR3's audit existed to stop. Worth a
look during SR40's walk: 12% is tuned for fills, and if the envelope reads as
too faint against the candles the fix belongs in `tokens.css`, not here.

**A null indicator value becomes WHITESPACE, `{ time }` with no `value`.** Zero
is the trap: it does not merely draw a wrong point, it pulls the price scale
down to include 0 and flattens every candle on the pane into a band at the top.
The same rule governs SR37's panes.

**The profile scales to its own widest bin, never to a constant.** It has no
axis and never gets one, so the only information in a bar's length is how it
compares with its neighbours — an absolute scale would make the same
distribution look different on every ticker. It caps at 18% of the pane width;
past that it stops annotating the candles and starts hiding them.

**Bin height comes from the spacing of the first two bins,** because the server
bins evenly. A lone bin has no neighbour, so it falls back to 1% of its own
price rather than a fixed number of dollars — a fixed span would give a $4 and
a $400 ticker bars three orders of magnitude apart in weight. Bars are also
floored at one pixel: a hundred-bin profile on a short pane rounds several to
zero height, which drops them silently.

**`chart-theme.ts` gained `info` and `infoSoft`.** Two palette entries, checked
by the existing "leaves no entry empty" test, which is the only reason the
theme file is touched outside SR35.

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
