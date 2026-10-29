# UI shell cockpit (v203), part 2: the dock's sections, the dock, edge tab, strip and sheet

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [UI redesign Phase 1: six-destination IA and the cockpit shell](../specs/2026-10-29-v202-ui-shell-cockpit-design.md) (§3 "Live", §4 "Plans awaiting order", "Portfolio heat", "Activity", "Data source", "Open/collapsed state", "Live strip", §6, §8 "Dock", "Strip and sheet")
**Index:** [`2026-10-29-v203-ui-shell-cockpit-dock_0-index.md`](2026-10-29-v203-ui-shell-cockpit-dock_0-index.md). Its Global Constraints, Parallelisation, task ledger and cross-task contracts apply to every task here.

Part 2 holds V203-5 … V203-8 in id order. V203-7b and V203-8b are splits that keep each task under 20 KB: the `X` task builds the components, the `Xb` task wires them into the shell. `<wt>` is the plan's worktree root (absolute). FE paths are relative to `frontend/src/app/` unless they start with `frontend/`.

Consumed from part 1 (final there): the `/live` SPA types and `LiveStore` (V203-2), the live-state rules (V203-3), `DockState` (V203-3b) and `LiveBotSection` (V203-4). Every dock section reuses V203-4's look: a `section.live-section[aria-labelledby]` with an `h2.title`, `--text-table` rows, and `--warn` for a warning (no new colour, Phase 1).

---

### Task V203-5: Dock Plans-awaiting section

**Model:** sonnet — one pure-input component over a small view builder, every word given here.

Ledger task V203-5 is split in two to stay under 20 KB: this half is the Plans-awaiting section, V203-5b the Portfolio-heat section. The two have disjoint files and may run in parallel.

**Files:**
- Create: `frontend/src/app/shell/live/live-awaiting-section.ts`, `frontend/src/app/shell/live/live-awaiting-section.spec.ts`

**Interfaces:**
- Consumes: `LiveAwaiting` (V203-2, `api/models.ts`); `isStale`, `liveTime` (V203-3, `shell/live/live-state.ts`).
- Produces (index ledger, final): `LiveAwaitingSection` (`sb-live-awaiting`), inputs `awaiting: LiveAwaiting | null`, `loading: boolean`, `now: Date`. Also exported, for its own spec only: `awaitingView`, `AwaitingView`, `AwaitingState`, `expiryDay`. V203-7's dock feeds it from `LiveStore.awaiting()`, `LiveStore.loading()` and the shell clock.

The words (spec v202 §4.2, §6):

| State | Shows |
|---|---|
| `awaiting` null while loading | `Loading…` |
| null and not loading (the first `/live` failed), `availability !== 'ok'`, or `count` null | `Plans unavailable` (` · reason` when given) |
| `count` 0 | `0 awaiting order`, and the as-of line |
| `count` > 0 | `3 awaiting order`; `Next expires 30 Oct` only when `next_expiry` is set (the Berlin day; session-dated plans only, never a guess for bar-count plans); the link `Show in Book ›` to `/trades?status=PENDING`; the as-of line |
| as-of line | `As of 13:54 · 6m ago` (`liveTime`), warning-toned when `as_of` is older than the 900 s rule (`isStale`). `LiveStore` keeps the last good snapshot after a failed refresh, so the age is what shows it going old |

It is a state count, not a since-last-visit badge: nothing here clears on view. The link's query is the Book's own filter vocabulary (`workspaces/trades/trades.ts`: `{ value: 'PENDING', label: 'Pending', param: 'status' }`).

- [ ] **Step 1: Write the failing spec**

Create `shell/live/live-awaiting-section.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveAwaiting } from '../../api/models';
import { LiveAwaitingSection, awaitingView, expiryDay } from './live-awaiting-section';

const NOW = new Date('2026-10-29T13:00:00Z');              // 14:00 Berlin
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const awaiting = (over: Partial<LiveAwaiting> = {}): LiveAwaiting => ({
  availability: 'ok', as_of: ago(6), reason: null, count: 3, next_expiry: '2026-10-30T20:00:00+00:00', ...over,
});

describe('expiryDay', () => {
  it('prints the Berlin calendar day', () => expect(expiryDay('2026-10-30T20:00:00+00:00')).toBe('30 Oct'));
  it('crosses midnight in Berlin, not in UTC', () => expect(expiryDay('2026-10-30T23:30:00Z')).toBe('31 Oct'));
  it.each([[null], [''], ['garbage']])('is null for %s', (iso) => expect(expiryDay(iso)).toBeNull());
});

describe('awaitingView (spec v202 §4.2, §6)', () => {
  it('is loading before the first answer, and unavailable when that answer failed', () => {
    expect(awaitingView(null, true, NOW).state).toBe('loading');
    expect(awaitingView(null, false, NOW).state).toBe('unavailable');
  });
  it.each<[Partial<LiveAwaiting>]>([[{ availability: 'unavailable', count: null, reason: 'db down' }], [{ count: null }]])(
    'is unavailable for %o', (change) => expect(awaitingView(awaiting(change), false, NOW).state).toBe('unavailable'));
  it('is empty at zero, and ok above it', () => {
    expect(awaitingView(awaiting({ count: 0, next_expiry: null }), false, NOW).state).toBe('empty');
    expect(awaitingView(awaiting(), false, NOW)).toEqual({
      state: 'ok', count: 3, expiry: '30 Oct', reason: null, asOf: '13:54 · 6m ago', stale: false,
    });
  });
  it('guesses no expiry for bar-count plans', () => expect(awaitingView(awaiting({ next_expiry: null }), false, NOW).expiry).toBeNull());
  it('marks a snapshot older than 900 s as stale', () => {
    expect(awaitingView(awaiting({ as_of: ago(16) }), false, NOW).stale).toBe(true);
    expect(awaitingView(awaiting({ as_of: ago(14) }), false, NOW).stale).toBe(false);
  });
});

describe('LiveAwaitingSection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] }));

  function mount(value: LiveAwaiting | null, loading = false) {
    const fixture = TestBed.createComponent(LiveAwaitingSection);
    fixture.componentRef.setInput('awaiting', value);
    fixture.componentRef.setInput('loading', loading);
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }
  const text = (node: Element) => node.textContent!.replace(/\s+/g, ' ').trim();

  it('titles the section', () => {
    const section = mount(awaiting()).querySelector('section[aria-labelledby]')!;
    expect(section.querySelector(`#${section.getAttribute('aria-labelledby')}`)!.textContent!.trim()).toBe('Plans awaiting order');
  });

  it('shows the count, the next expiry and a link to the pending plans in the Book', () => {
    const el = mount(awaiting());
    expect(text(el.querySelector('.figure')!)).toBe('3 awaiting order');
    expect(text(el.querySelector('.note')!)).toBe('Next expires 30 Oct');
    const link = el.querySelector<HTMLAnchorElement>('a.link')!;
    expect(link.getAttribute('href')).toBe('/trades?status=PENDING');
    expect(link.textContent!.trim()).toBe('Show in Book ›');
    expect(link.classList).toContain('sb-hit');
    expect(text(el.querySelector('.as-of')!)).toBe('As of 13:54 · 6m ago');
  });

  it('shows zero without a link or an expiry', () => {
    const el = mount(awaiting({ count: 0, next_expiry: null }));
    expect(text(el.querySelector('.figure')!)).toBe('0 awaiting order');
    expect(el.querySelector('a.link')).toBeNull();
    expect(el.querySelector('.note')).toBeNull();
  });

  it('says loading, and says unavailable with the reason', () => {
    expect(text(mount(null, true).querySelector('[role=status]')!)).toBe('Loading…');
    const el = mount(awaiting({ availability: 'unavailable', count: null, reason: 'db down' }));
    expect(text(el.querySelector('.muted')!)).toBe('Plans unavailable · db down');
    expect(el.querySelector('.as-of')).toBeNull();
  });

  it('tones a stale as-of line', () => {
    expect(mount(awaiting({ as_of: ago(30) })).querySelector('.as-of')!.classList).toContain('warn');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-awaiting-section.spec.ts
```

Expected: FAIL to compile: `./live-awaiting-section` does not exist.

- [ ] **Step 3: Write the section**

Create `shell/live/live-awaiting-section.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { LiveAwaiting } from '../../api/models';
import { isStale, liveTime } from './live-state';

export type AwaitingState = 'loading' | 'unavailable' | 'empty' | 'ok';
export interface AwaitingView {
  state: AwaitingState; count: number | null; expiry: string | null;
  reason: string | null; asOf: string; stale: boolean;
}

/** '30 Oct': the Berlin day a session-dated plan expires; null when none. */
export function expiryDay(iso: string | null): string | null {
  const at = iso ? new Date(iso) : null;
  if (at === null || Number.isNaN(at.getTime())) return null;
  return at.toLocaleDateString('en-GB', { timeZone: 'Europe/Berlin', day: 'numeric', month: 'short' });
}

function awaitingState(a: LiveAwaiting | null, loading: boolean): AwaitingState {
  if (a === null) return loading ? 'loading' : 'unavailable';
  if (a.availability !== 'ok' || a.count === null) return 'unavailable';
  return a.count === 0 ? 'empty' : 'ok';
}

/** What the section shows, from the /live awaiting block. */
export function awaitingView(a: LiveAwaiting | null, loading: boolean, now: Date): AwaitingView {
  return {
    state: awaitingState(a, loading),
    count: a?.count ?? null,
    expiry: expiryDay(a?.next_expiry ?? null),
    reason: a?.reason ?? null,
    asOf: liveTime(a?.as_of ?? null, now),
    stale: a !== null && isStale(a.as_of, now),
  };
}

let nextId = 0;

/**
 * Plans awaiting order -- v203 (spec v202 §4.2). A state count of PENDING
 * plans, never a since-last-visit badge: it drops only when a plan fills,
 * expires or is cancelled. The next expiry shows only for plans that carry
 * `valid_session`, where it is exact; bar-count plans get no guess.
 */
@Component({
  selector: 'sb-live-awaiting',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Plans awaiting order</h2>
      @switch (view().state) {
        @case ('loading') { <p class="muted" role="status">Loading…</p> }
        @case ('unavailable') {
          <p class="muted">Plans unavailable@if (view().reason; as reason) { · {{ reason }}}</p>
        }
        @default {
          <p class="figure"><span class="count">{{ view().count }}</span> awaiting order</p>
          @if (view().state === 'ok') {
            @if (view().expiry; as expiry) { <p class="note">Next expires {{ expiry }}</p> }
            <a class="link sb-hit" routerLink="/trades" [queryParams]="pendingParams">Show in Book ›</a>
          }
          <p class="as-of" [class.warn]="view().stale">As of {{ view().asOf }}</p>
        }
      }
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    p { margin: 0 0 var(--space-4); font-size: var(--text-table); overflow-wrap: anywhere; }
    .figure { color: var(--text-secondary); }
    .count { color: var(--text); font-size: var(--text-body); font-weight: 600; font-variant-numeric: tabular-nums; }
    .note, .muted, .as-of { color: var(--text-muted); }
    .as-of.warn { color: var(--warn); }
    .link { display: inline-flex; align-items: center; min-height: var(--control-h); color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .link:hover { text-decoration: underline; }
  `,
})
export class LiveAwaitingSection {
  readonly awaiting = input<LiveAwaiting | null>(null);
  readonly loading = input(false);
  readonly now = input.required<Date>();

  protected readonly headingId = `live-awaiting-${nextId++}`;
  /** The Book's own filter vocabulary (trades.ts: `{ value: 'PENDING', param: 'status' }`). */
  protected readonly pendingParams = { status: 'PENDING' };
  protected readonly view = computed(() => awaitingView(this.awaiting(), this.loading(), this.now()));
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-awaiting-section.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean.

Complexity: `awaitingState` 5, `awaitingView` 4, `expiryDay` 4.

Layout: no screen renders this section until V203-7b mounts the dock (desktop) and V203-8b the sheet (tablet, phone). Their three-width audits cover it, so record in the report that the visual check is deferred to those tasks. The link is `sb-hit` with `min-height: var(--control-h)`, which the touch block raises to 44 px.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-awaiting-section.ts frontend/src/app/shell/live/live-awaiting-section.spec.ts
git -C <wt> commit -m "feat(v203): the dock's Plans-awaiting section

The PENDING count as a state, never a since-last-visit badge; the next
expiry only for session-dated plans, where it is exact; a link to those
plans in the Book; and an as-of age that turns amber once the snapshot
is older than 900 s.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-5b: Dock Portfolio-heat section

**Model:** sonnet — one pure-input component over small text builders, every word given here.

The second half of ledger task V203-5, split to stay under 20 KB. Its files are disjoint from V203-5's, so the two may run in parallel.

**Files:**
- Create: `frontend/src/app/shell/live/live-heat-section.ts`, `frontend/src/app/shell/live/live-heat-section.spec.ts`

**Interfaces:**
- Consumes: `LiveHeat` (V203-2, `api/models.ts`); `isStale`, `liveTime`, `heatTone`, `HeatTone` (V203-3, `shell/live/live-state.ts`); `amount`, `ABSENT` (`ui/format.ts`); `PanelError` (`sb-panel-error`, `ui/panel-error.ts`: input `message`, output `retry`).
- Produces (index ledger, final): `LiveHeatSection` (`sb-live-heat`), inputs `heat: LiveHeat | null`, `loading: boolean`, `currency: string`, `now: Date`; output `retry: void`. Also exported, for its own spec only: `heatView`, `HeatView`, `HeatState`, `atRiskText`, `roomText`, `utilisationText`. V203-7's dock feeds it from `LiveStore.heat()`, `LiveStore.loading()`, `ConnectionStore.currency()` and the shell clock, and wires `retry` to `LiveStore.retry()`.

The words (spec v202 §4.3, §6):

| State | Shows |
|---|---|
| `heat` null while loading | `Loading…` |
| null and not loading, `availability !== 'ok'`, or `open_pct`/`cap_pct` null | `sb-panel-error` reading `Heat unavailable` (plus ` (reason)`); its Retry emits `retry` |
| ok | `2,010 € at risk · 4.2% of 48,210 € · cap 6% (2,893 €)`; a meter; `70% of the cap` (`130% of the cap · Over cap` above 100 %); `Room 883 € · 1.8% under the cap`, or `Over cap by 867 € · 1.8%` when the headroom is negative; `incl. resting orders` when `includes_resting`; the as-of line |
| as-of line | `As of 13:54 · 6m ago` (`liveTime`), warning-toned when `as_of` is older than the 900 s rule (`isStale`) |

Money goes through `amount(value, currency, 0)` (unit after the figure, the controller's decision for every dock amount). Percent prints one decimal at most (`4.2%`, `6%`). Nothing is clamped except the meter's fill width (0–100 %), as on the Risk page. The figure, the meter fill and the utilisation line take `--warn` from 80 % of the cap (`heatTone` `near` or `over`); never red in Phase 1. Heat is `/live`'s, which v202 computes with the Risk page's own `heat.open_heat`, so it includes resting orders exactly as Risk does.

- [ ] **Step 1: Write the failing spec**

Create `shell/live/live-heat-section.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveHeat } from '../../api/models';
import { LiveHeatSection, atRiskText, heatView, roomText, utilisationText } from './live-heat-section';

const NOW = new Date('2026-10-29T13:00:00Z');
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const heat = (over: Partial<LiveHeat> = {}): LiveHeat => ({
  availability: 'ok', as_of: ago(6), reason: null, open_pct: 4.2, cap_pct: 6, utilisation_pct: 70, open_amount: 2010,
  cap_amount: 2893, headroom_pct: 1.8, headroom_amount: 883, balance: 48210, includes_resting: true, ...over,
});
const OVER: Partial<LiveHeat> = { open_pct: 7.8, utilisation_pct: 130, open_amount: 3760, headroom_pct: -1.8, headroom_amount: -867 };

describe('heat words (spec v202 §4.3)', () => {
  it('reads dollars and percent against the balance and the cap', () => {
    expect(atRiskText(heat(), '€')).toBe('2,010 € at risk · 4.2% of 48,210 € · cap 6% (2,893 €)');
  });
  it('drops only the words a missing figure would print', () => {
    expect(atRiskText(heat({ open_amount: null, balance: null, cap_amount: null }), '€')).toBe('At risk · 4.2% · cap 6%');
    expect(atRiskText(heat({ open_pct: null }), '€')).toBe('—');
  });
  it('reads the room left, or how far over the cap', () => {
    expect(roomText(heat(), '€')).toBe('Room 883 € · 1.8% under the cap');
    expect(roomText(heat(OVER), '€')).toBe('Over cap by 867 € · 1.8%');
    expect(roomText(heat({ headroom_amount: null }), '€')).toBe('Room 1.8% under the cap');
    expect(roomText(heat({ headroom_pct: null }), '€')).toBe('—');
  });
  it.each<[number | null, string]>([[70, '70% of the cap'], [80, '80% of the cap'], [100, '100% of the cap'],
    [130, '130% of the cap · Over cap'], [null, '—']])('never clamps: %s reads %s', (pct, words) => expect(utilisationText(pct)).toBe(words));
});

describe('heatView', () => {
  it('is loading, then unavailable when the first answer failed', () => {
    expect(heatView(null, true, '€', NOW).state).toBe('loading');
    expect(heatView(null, false, '€', NOW)).toMatchObject({ state: 'unavailable', message: 'Heat unavailable' });
  });
  it.each<[Partial<LiveHeat>, string]>([
    [{ availability: 'unavailable', reason: 'no balance' }, 'Heat unavailable (no balance)'],
    [{ open_pct: null }, 'Heat unavailable'],
    [{ cap_pct: null }, 'Heat unavailable'],
  ])('is unavailable for %o', (change, message) => {
    expect(heatView(heat(change), false, '€', NOW)).toMatchObject({ state: 'unavailable', message });
  });
  it.each<[number, string, number]>([[70, 'ok', 70], [80, 'near', 80], [130, 'over', 100], [-5, 'ok', 0]])(
    'tones utilisation %s as %s and fills the meter to %s', (pct, tone, width) => {
      expect(heatView(heat({ utilisation_pct: pct }), false, '€', NOW)).toMatchObject({ state: 'ok', tone, meterWidth: width, utilisationPct: pct });
    });
  it('marks resting orders and a stale snapshot', () => {
    expect(heatView(heat(), false, '€', NOW)).toMatchObject({ resting: true, asOf: '13:54 · 6m ago', stale: false });
    expect(heatView(heat({ includes_resting: false, as_of: ago(20) }), false, '€', NOW)).toMatchObject({ resting: false, stale: true });
  });
});

describe('LiveHeatSection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(value: LiveHeat | null, loading = false) {
    const fixture = TestBed.createComponent(LiveHeatSection);
    fixture.componentRef.setInput('heat', value);
    fixture.componentRef.setInput('loading', loading);
    fixture.componentRef.setInput('currency', '€');
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }
  const text = (node: Element) => node.textContent!.replace(/\s+/g, ' ').trim();

  it('renders the figure, an unclamped meter, the room and the resting note', () => {
    const { el } = mount(heat());
    expect(text(el.querySelector('h2.title')!)).toBe('Portfolio heat');
    expect(text(el.querySelector('.at-risk')!)).toBe('2,010 € at risk · 4.2% of 48,210 € · cap 6% (2,893 €)');
    const meter = el.querySelector('[role=meter]')!;
    expect(meter.getAttribute('aria-valuenow')).toBe('70');
    expect(meter.getAttribute('aria-label')).toBe('Portfolio heat against the cap');
    expect(el.querySelector<HTMLElement>('.fill')!.style.width).toBe('70%');
    expect(text(el.querySelector('.room')!)).toBe('Room 883 € · 1.8% under the cap');
    expect(text(el.querySelector('.note')!)).toBe('incl. resting orders');
    expect(el.querySelectorAll('.warn').length).toBe(0);
  });

  it('turns amber at 80 % and says Over cap above 100 %, the meter value unclamped', () => {
    expect(mount(heat({ utilisation_pct: 80 })).el.querySelector('.at-risk')!.classList).toContain('warn');
    const { el } = mount(heat(OVER));
    expect(text(el.querySelector('.util')!)).toBe('130% of the cap · Over cap');
    expect(el.querySelector('[role=meter]')!.getAttribute('aria-valuenow')).toBe('130');
    expect(el.querySelector<HTMLElement>('.fill')!.style.width).toBe('100%');
    expect(el.querySelector('.fill')!.classList).toContain('warn');
  });

  it('shows the panel error with a retry when heat is unavailable', () => {
    const { fixture, el } = mount(heat({ availability: 'unavailable', open_pct: null, reason: 'db down' }));
    let retried = 0;
    fixture.componentInstance.retry.subscribe(() => retried++);
    expect(text(el.querySelector('sb-panel-error')!)).toContain('Heat unavailable (db down)');
    el.querySelector<HTMLButtonElement>('sb-panel-error button.retry')!.click();
    expect(retried).toBe(1);
    expect(el.querySelector('[role=meter]')).toBeNull();
  });

  it('says loading before the first answer', () => {
    expect(text(mount(null, true).el.querySelector('[role=status]')!)).toBe('Loading…');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-heat-section.spec.ts
```

Expected: FAIL to compile: `./live-heat-section` does not exist.

- [ ] **Step 3: Write the section**

Create `shell/live/live-heat-section.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { LiveHeat } from '../../api/models';
import { ABSENT, amount } from '../../ui/format';
import { PanelError } from '../../ui/panel-error';
import { HeatTone, heatTone, isStale, liveTime } from './live-state';

export type HeatState = 'loading' | 'unavailable' | 'ok';
export interface HeatView {
  state: HeatState; tone: HeatTone; atRisk: string; utilisation: string; room: string;
  utilisationPct: number | null; meterWidth: number; resting: boolean; message: string;
  asOf: string; stale: boolean;
}

const pctText = (value: number) => `${Number(value.toFixed(1))}%`;

/** '2,010 € at risk · 4.2% of 48,210 € · cap 6% (2,893 €)'. A missing
 *  amount drops only its own words; a missing percent gives '—'. */
export function atRiskText(h: LiveHeat, currency: string): string {
  if (h.open_pct === null || h.cap_pct === null) return ABSENT;
  const lead = h.open_amount === null ? 'At risk' : `${amount(h.open_amount, currency, 0)} at risk`;
  const share = h.balance === null ? pctText(h.open_pct) : `${pctText(h.open_pct)} of ${amount(h.balance, currency, 0)}`;
  const cap = h.cap_amount === null ? `cap ${pctText(h.cap_pct)}` : `cap ${pctText(h.cap_pct)} (${amount(h.cap_amount, currency, 0)})`;
  return `${lead} · ${share} · ${cap}`;
}

/** 'Room 883 € · 1.8% under the cap', or 'Over cap by 867 € · 1.8%' when the headroom is negative. */
export function roomText(h: LiveHeat, currency: string): string {
  if (h.headroom_pct === null) return ABSENT;
  const money = h.headroom_amount === null ? '' : `${amount(Math.abs(h.headroom_amount), currency, 0)} · `;
  return h.headroom_pct < 0
    ? `Over cap by ${money}${pctText(-h.headroom_pct)}`
    : `Room ${money}${pctText(h.headroom_pct)} under the cap`;
}

/** '70% of the cap'; above 100 % it adds ' · Over cap', so near and over never look alike. Never clamped. */
export function utilisationText(utilisationPct: number | null): string {
  if (utilisationPct === null) return ABSENT;
  const words = `${pctText(utilisationPct)} of the cap`;
  return heatTone(utilisationPct) === 'over' ? `${words} · Over cap` : words;
}

function heatState(h: LiveHeat | null, loading: boolean): HeatState {
  if (h === null) return loading ? 'loading' : 'unavailable';
  return h.availability === 'ok' && h.open_pct !== null && h.cap_pct !== null ? 'ok' : 'unavailable';
}

/** Only the meter's WIDTH is clamped (as on the Risk page); every number printed is not. */
const meterWidth = (pct: number | null) => Math.min(100, Math.max(0, pct ?? 0));

/** What the section shows, from the /live heat block. */
export function heatView(h: LiveHeat | null, loading: boolean, currency: string, now: Date): HeatView {
  const pct = h?.utilisation_pct ?? null;
  return {
    state: heatState(h, loading),
    tone: heatTone(pct),
    atRisk: h ? atRiskText(h, currency) : ABSENT,
    utilisation: utilisationText(pct),
    room: h ? roomText(h, currency) : ABSENT,
    utilisationPct: pct,
    meterWidth: meterWidth(pct),
    resting: h?.includes_resting === true,
    message: h?.reason ? `Heat unavailable (${h.reason})` : 'Heat unavailable',
    asOf: liveTime(h?.as_of ?? null, now),
    stale: h !== null && isStale(h.as_of, now),
  };
}

let nextId = 0;

/**
 * Portfolio heat -- v203 (spec v202 §4.3). Exactly the Risk page's heat
 * (v202's /live computes it with the same `heat.open_heat`), read from
 * /live only: this component never sees RiskStore. Amber from 80 % of the
 * cap, "Over cap" in words above 100 %, never red in Phase 1.
 */
@Component({
  selector: 'sb-live-heat',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PanelError],
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Portfolio heat</h2>
      @switch (view().state) {
        @case ('loading') { <p class="muted" role="status">Loading…</p> }
        @case ('unavailable') { <sb-panel-error [message]="view().message" (retry)="retry.emit()" /> }
        @default {
          <p class="at-risk" [class.warn]="warn()">{{ view().atRisk }}</p>
          <div class="track" role="meter" aria-label="Portfolio heat against the cap"
               [attr.aria-valuenow]="view().utilisationPct" aria-valuemin="0" aria-valuemax="100"
               [attr.aria-valuetext]="view().utilisation">
            <span class="fill" [class.warn]="warn()" [style.width.%]="view().meterWidth"></span>
          </div>
          <p class="util" [class.warn]="warn()">{{ view().utilisation }}</p>
          <p class="room">{{ view().room }}</p>
          @if (view().resting) { <p class="note">incl. resting orders</p> }
          <p class="as-of" [class.warn]="view().stale">As of {{ view().asOf }}</p>
        }
      }
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    p { margin: 0 0 var(--space-4); font-size: var(--text-table); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
    .at-risk { color: var(--text); }
    .util, .room { color: var(--text-secondary); }
    .note, .muted, .as-of { color: var(--text-muted); }
    .warn, .as-of.warn { color: var(--warn); }
    .track { height: 6px; margin: var(--space-6) 0; border-radius: 3px; background: var(--border); overflow: hidden; }
    .fill { display: block; height: 100%; background: var(--text-muted); }
    .fill.warn { background: var(--warn); }
  `,
})
export class LiveHeatSection {
  readonly heat = input<LiveHeat | null>(null);
  readonly loading = input(false);
  readonly currency = input.required<string>();
  readonly now = input.required<Date>();
  readonly retry = output<void>();

  protected readonly headingId = `live-heat-${nextId++}`;
  protected readonly view = computed(() => heatView(this.heat(), this.loading(), this.currency(), this.now()));
  protected readonly warn = computed(() => this.view().tone === 'near' || this.view().tone === 'over');
}
```

The track and fill copy the Risk page's meter (`workspaces/risk/risk.ts`: `.fill` on `--text-muted`, `.fill.warn` on `--warn`), so the two read alike without a new style.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-heat-section.spec.ts
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean.

Complexity: `heatView` 7 (optional chains and `?:` count), `atRiskText` 5, `heatState` 5, `roomText` 4, `utilisationText` 3.

Layout: no screen renders this section until V203-7b mounts the dock (desktop) and V203-8b the sheet (tablet, phone). Their three-width audits cover it, so record in the report that the visual check is deferred to those tasks. The Retry control is `sb-panel-error`'s, sized by `--control-h` (44 px under the touch block).

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-heat-section.ts frontend/src/app/shell/live/live-heat-section.spec.ts
git -C <wt> commit -m "feat(v203): the dock's Portfolio-heat section

Dollars and percent against the balance and the cap, an unclamped
reading over a clamped meter, the room left or how far over, amber from
80 % and \"Over cap\" above 100 %, \"incl. resting orders\", the panel
error with a retry when heat is unavailable, and an as-of age that
turns amber once the snapshot is older than 900 s.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-6: Dock Activity rules (line, partial, "No scan since", state)

**Model:** sonnet — pure table-driven builders, every word given here.

Ledger task V203-6 is split in two to stay under 20 KB: this half writes the pure builders the Activity section shows, V203-6b the `sb-live-activity` component on top of them in the same file. V203-6b runs straight after this task.

**Files:**
- Create: `frontend/src/app/shell/live/live-activity-section.ts` (builders only here), `frontend/src/app/shell/live/live-activity-section.spec.ts`

**Interfaces:**
- Consumes: `LiveEvent`, `LiveEventKind`, `LiveEventsMeta`, `LiveTone` (V203-2, `api/models.ts`); `isStale`, `liveTime` (V203-3); `scanAge` (`shell/freshness-chip.ts`); `amount`, `MINUS`, `timeInZone` (`ui/format.ts`).
- Produces (index ledger, final): `activityLine(e: LiveEvent, currency?: string): string`, exported. The optional `currency` (default `'€'`, `ConnectionStore.currency()`'s own fallback) is additive: every dock amount carries the account's unit (controller decision), and `activityLine(e)` still holds. Also exported, for V203-6b and the specs: `PnlParts`, `ActivityRow`, `ActivityView`, `pnlParts(pnl, currency): PnlParts | null`, `missingText(meta): string | null`, `activityView(events, meta, loading, lastSuccess, now, currency): ActivityView`.


| Situation | Shows |
|---|---|
| `meta` null while loading | `Loading…` |
| `meta` null and not loading (the first `/live` failed), or `meta.availability === 'unavailable'` | `sb-panel-error` reading `Activity unavailable`; its Retry emits `retry` |
| a row | time and age (`liveTime`: `13:54 · 6m ago`), a tone dot, the server's one-line `text`, then for a P&L row ` · +2.1R (441 €) (paper, pre-cost)`: the R in its tone colour, the amount in the neutral text colour; `+2.1R (paper, pre-cost)` when `pnl.amount` is null |
| `availability === 'partial'` | the rows, then a faint `Some sources unavailable: TP1 hits` (kinds worded: `plan_alerted` alerts, `paper_filled` paper fills, `tp1_hit` TP1 hits, `trade_closed` closes, `killswitch` killswitch) |
| last success older than the 900 s rule | `No scan since 09:00 (5h ago)` in warning tone (Berlin time, `scanAge` age), above any rows: a missed scan never reads as a quiet day. With no success at all, `No scan yet` |
| no rows and the scan is fresh | `Nothing yet today` |
| always (after loading) | the link `Full activity log →` to System → Logs (`/system?tab=logs`) |

The R prints one decimal with a true minus (`MINUS`, `ui/format.ts`) for a loss: `−1.0R (210 €)`. The amount is unsigned `amount(|x|, currency, 0)`; the R carries the sign. The event `text` never carries P&L (v202 contract), so nothing is printed twice.


- [ ] **Step 1: Write the failing spec**

Create `shell/live/live-activity-section.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { LiveEvent, LiveEventsMeta } from '../../api/models';
import { activityLine, activityView, missingText, pnlParts } from './live-activity-section';

const NOW = new Date('2026-10-29T13:00:00Z');               // 14:00 Berlin
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const event = (over: Partial<LiveEvent> = {}): LiveEvent => ({
  at: ago(6), kind: 'trade_closed', text: 'NVDA closed · TP2', tone: 'positive', ref: '812', pnl: { r: 2.1, amount: 441 }, ...over,
});
const ALERT = event({ kind: 'plan_alerted', text: 'AAPL plan alerted · long', tone: 'info', pnl: null, at: ago(20) });
const meta = (over: Partial<LiveEventsMeta> = {}): LiveEventsMeta => ({ availability: 'ok', as_of: ago(0), missing: [], ...over });

describe('activityLine (spec v202 §4.4)', () => {
  it('appends R, its amount and the paper label to a P&L row', () => {
    expect(activityLine(event())).toBe('NVDA closed · TP2 · +2.1R (441 €) (paper, pre-cost)');
    expect(activityLine(event(), '$')).toBe('NVDA closed · TP2 · +2.1R (441 $) (paper, pre-cost)');
  });
  it('signs a loss with a true minus and keeps the amount unsigned', () => {
    expect(activityLine(event({ pnl: { r: -1, amount: -210 }, tone: 'negative' }))).toBe('NVDA closed · TP2 · −1.0R (210 €) (paper, pre-cost)');
  });
  it('omits a missing amount, and leaves a row without P&L alone', () => {
    expect(activityLine(event({ pnl: { r: 1, amount: null } }))).toBe('NVDA closed · TP2 · +1.0R (paper, pre-cost)');
    expect(activityLine(ALERT)).toBe('AAPL plan alerted · long');
    expect(pnlParts(null, '€')).toBeNull();
  });
});

describe('missingText', () => {
  it('words the kinds of a failed source', () => {
    expect(missingText(meta({ availability: 'partial', missing: ['tp1_hit', 'paper_filled'] }))).toBe('Some sources unavailable: TP1 hits, paper fills');
    expect(missingText(meta({ availability: 'partial', missing: [] }))).toBe('Some sources unavailable');
    expect(missingText(meta())).toBeNull();
  });
});

describe('activityView (spec v202 §6)', () => {
  it('is loading, then unavailable when the first answer failed or the source is down', () => {
    expect(activityView([], null, true, ago(2), NOW, '€').state).toBe('loading');
    expect(activityView([], null, false, ago(2), NOW, '€').state).toBe('unavailable');
    expect(activityView([], meta({ availability: 'unavailable' }), false, ago(2), NOW, '€').state).toBe('unavailable');
  });
  it('reads Nothing yet today only with no rows and a recent scan', () => {
    expect(activityView([], meta(), false, ago(2), NOW, '€')).toMatchObject({ state: 'ok', quiet: true, scanWarning: null });
    expect(activityView([ALERT], meta(), false, ago(2), NOW, '€').quiet).toBe(false);
  });
  it('never reads a missed scan as a quiet day', () => {
    expect(activityView([], meta(), false, ago(300), NOW, '€')).toMatchObject({ quiet: false, scanWarning: 'No scan since 09:00 (5h ago)' });
    expect(activityView([ALERT], meta(), false, ago(300), NOW, '€').scanWarning).toBe('No scan since 09:00 (5h ago)');
    expect(activityView([], meta(), false, null, NOW, '€')).toMatchObject({ quiet: false, scanWarning: 'No scan yet' });
  });
  it('builds a row per event with its time, tone and P&L parts', () => {
    expect(activityView([event()], meta(), false, ago(2), NOW, '€').rows).toEqual([{
      key: `${ago(6)}|trade_closed|812`, time: '13:54 · 6m ago', text: 'NVDA closed · TP2', tone: 'positive',
      pnl: { r: '+2.1R', amount: '441 €' }, line: 'NVDA closed · TP2 · +2.1R (441 €) (paper, pre-cost)',
    }]);
  });
});

```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-activity-section.spec.ts
```

Expected: FAIL to compile: `./live-activity-section` does not exist.

- [ ] **Step 3: Write the builders**

Create `shell/live/live-activity-section.ts` (V203-6b appends the component below them):

```ts
import { LiveEvent, LiveEventKind, LiveEventsMeta, LiveTone } from '../../api/models';
import { MINUS, amount, timeInZone } from '../../ui/format';
import { scanAge } from '../freshness-chip';
import { isStale, liveTime } from './live-state';

export interface PnlParts { r: string; amount: string | null; }
export interface ActivityRow { key: string; time: string; text: string; tone: LiveTone; pnl: PnlParts | null; line: string; }
export interface ActivityView {
  state: 'loading' | 'unavailable' | 'ok'; rows: ActivityRow[];
  missing: string | null; scanWarning: string | null; quiet: boolean;
}

const DEFAULT_CURRENCY = '€';           // ConnectionStore.currency()'s own fallback
const PAPER = '(paper, pre-cost)';
const KIND_WORDS: Readonly<Record<LiveEventKind, string>> = {
  plan_alerted: 'alerts', paper_filled: 'paper fills', tp1_hit: 'TP1 hits', trade_closed: 'closes', killswitch: 'killswitch',
};

function signOf(value: number): string {
  if (value > 0) return '+';
  return value < 0 ? MINUS : '';
}

/** '+2.1R' and '441 €' (unsigned: the R carries the sign); null without P&L. */
export function pnlParts(pnl: LiveEvent['pnl'], currency: string): PnlParts | null {
  if (pnl === null) return null;
  return {
    r: `${signOf(pnl.r)}${Math.abs(pnl.r).toFixed(1)}R`,
    amount: pnl.amount === null ? null : amount(Math.abs(pnl.amount), currency, 0),
  };
}

/** The row's one line: the server's text, then ' · +2.1R (441 €) (paper, pre-cost)' for a P&L row. */
export function activityLine(e: LiveEvent, currency: string = DEFAULT_CURRENCY): string {
  const parts = pnlParts(e.pnl, currency);
  if (parts === null) return e.text;
  return parts.amount === null ? `${e.text} · ${parts.r} ${PAPER}` : `${e.text} · ${parts.r} (${parts.amount}) ${PAPER}`;
}

/** 'Some sources unavailable: TP1 hits' for a partial read; null otherwise. */
export function missingText(meta: LiveEventsMeta | null): string | null {
  if (meta?.availability !== 'partial') return null;
  const words = meta.missing.map((kind) => KIND_WORDS[kind]);
  return words.length ? `Some sources unavailable: ${words.join(', ')}` : 'Some sources unavailable';
}

/** 'No scan since 09:00 (5h ago)' once the last success is past the 900 s rule; null while fresh. */
function scanWarning(lastSuccess: string | null, now: Date): string | null {
  if (!isStale(lastSuccess, now)) return null;
  const age = scanAge(lastSuccess, now.getTime());
  return age === null ? 'No scan yet' : `No scan since ${timeInZone(lastSuccess, 'Europe/Berlin')} (${age})`;
}

function activityState(meta: LiveEventsMeta | null, loading: boolean): ActivityView['state'] {
  if (meta === null) return loading ? 'loading' : 'unavailable';
  return meta.availability === 'unavailable' ? 'unavailable' : 'ok';
}

function rowOf(e: LiveEvent, now: Date, currency: string): ActivityRow {
  return {
    key: `${e.at}|${e.kind}|${e.ref ?? ''}`, time: liveTime(e.at, now), text: e.text, tone: e.tone,
    pnl: pnlParts(e.pnl, currency), line: activityLine(e, currency),
  };
}

/** What the section shows (spec v202 §6): a missed scan is never a quiet day. */
export function activityView(
  events: readonly LiveEvent[], meta: LiveEventsMeta | null, loading: boolean,
  lastSuccess: string | null, now: Date, currency: string,
): ActivityView {
  const rows = events.map((e) => rowOf(e, now, currency));
  const warning = scanWarning(lastSuccess, now);
  const state = activityState(meta, loading);
  return { state, rows, missing: missingText(meta), scanWarning: warning, quiet: state === 'ok' && rows.length === 0 && warning === null };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-activity-section.spec.ts
```
```bash
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean.

Complexity: `activityLine` 3, `pnlParts` 3, `signOf` 3, `missingText` 3, `scanWarning` 3, `activityView` 3, `activityState` 4, `rowOf` 2.

Layout: no UI in this task. V203-6b renders these, and V203-7b and V203-8b check them at three widths.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-activity-section.ts frontend/src/app/shell/live/live-activity-section.spec.ts
git -C <wt> commit -m "feat(v203): the dock's Activity rules

One line per event, with R, its amount and \"(paper, pre-cost)\" on P&L
rows; the partial-read line naming the failed sources; and the
\"No scan since 09:00 (5h ago)\" warning, so a missed scan never reads
as \"Nothing yet today\".

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V203-6b: Dock Activity section component

**Model:** sonnet — one pure-input component over V203-6's builders; markup and styles given here.

The second half of ledger task V203-6, split to stay under 20 KB. It runs straight after V203-6.

**Files:**
- Modify: `frontend/src/app/shell/live/live-activity-section.ts` (append the component), `frontend/src/app/shell/live/live-activity-section.spec.ts` (append its describe)

**Interfaces:**
- Consumes: `activityView`, `ActivityView` (V203-6, same file); `PanelError` (`ui/panel-error.ts`: input `message`, output `retry`); `RouterLink`.
- Produces (index ledger, final): `LiveActivitySection` (`sb-live-activity`), inputs `events: readonly LiveEvent[]`, `meta: LiveEventsMeta | null`, `loading: boolean`, `lastSuccess: string | null`, `now: Date`, plus the additive `currency: string` (default `'€'`); output `retry: void`. V203-7's dock feeds it from `LiveStore.events()`, `eventsMeta()`, `loading()`, `ConnectionStore.botLastSuccess()`, `currency()` and the shell clock, and wires `retry` to `LiveStore.retry()`.

Rendering, in order: the title `Activity`; `Loading…` (no link yet) or `sb-panel-error` reading `Activity unavailable`; else the `No scan since …` line (`.scan-warning.warn`, `role=status`), the `ol.events` rows (class `tone-<tone>`, a dot, `<time>`, `.line` reading exactly `activityLine`), `Nothing yet today` (`.quiet`) and the faint partial line right after the list; then, once loaded, the link `Full activity log →` to `/system?tab=logs` (`sb-hit`).

- [ ] **Step 1: Write the failing component spec**

In `shell/live/live-activity-section.spec.ts`, replace the import block with:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveEvent, LiveEventsMeta } from '../../api/models';
import { LiveActivitySection, activityLine, activityView, missingText, pnlParts } from './live-activity-section';
```

and append at the end of the file:

```ts
describe('LiveActivitySection', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] }));

  function mount(events: LiveEvent[], m: LiveEventsMeta | null, lastSuccess: string | null = ago(2), loading = false) {
    const fixture = TestBed.createComponent(LiveActivitySection);
    fixture.componentRef.setInput('events', events);
    fixture.componentRef.setInput('meta', m);
    fixture.componentRef.setInput('loading', loading);
    fixture.componentRef.setInput('lastSuccess', lastSuccess);
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }
  const text = (node: Element) => node.textContent!.replace(/\s+/g, ' ').trim();

  it('lists the events newest first as given, each line with its tone', () => {
    const { el } = mount([event(), ALERT], meta());
    expect(text(el.querySelector('h2.title')!)).toBe('Activity');
    const rows = [...el.querySelectorAll('ol.events > li')];
    expect(rows.map((row) => text(row.querySelector('.line')!))).toEqual([activityLine(event()), activityLine(ALERT)]);
    expect(rows.map((row) => text(row.querySelector('time')!))).toEqual(['13:54 · 6m ago', '13:40 · 20m ago']);
    expect(rows[0].classList).toContain('tone-positive');
    expect(rows[0].querySelector('.amt')!.classList).not.toContain('tone');
  });

  it('adds the faint partial line after the rows', () => {
    const { el } = mount([ALERT], meta({ availability: 'partial', missing: ['tp1_hit'] }));
    const faint = el.querySelector('ol.events + .faint')!;
    expect(text(faint)).toBe('Some sources unavailable: TP1 hits');
  });

  it('says Nothing yet today on a quiet, fresh day', () => {
    const { el } = mount([], meta());
    expect(text(el.querySelector('.quiet')!)).toBe('Nothing yet today');
    expect(el.querySelector('.scan-warning')).toBeNull();
  });

  it('warns No scan since 09:00 (5h ago) when the bot stopped, never Nothing yet today', () => {
    const { el } = mount([], meta(), ago(300));
    const warning = el.querySelector('.scan-warning')!;
    expect(text(warning)).toBe('No scan since 09:00 (5h ago)');
    expect(warning.classList).toContain('warn');
    expect(el.querySelector('.quiet')).toBeNull();
  });

  it('shows Activity unavailable with a retry, and still links the full log', () => {
    const { fixture, el } = mount([], meta({ availability: 'unavailable' }));
    let retried = 0;
    fixture.componentInstance.retry.subscribe(() => retried++);
    expect(text(el.querySelector('sb-panel-error')!)).toContain('Activity unavailable');
    el.querySelector<HTMLButtonElement>('sb-panel-error button.retry')!.click();
    expect(retried).toBe(1);
    const link = el.querySelector<HTMLAnchorElement>('a.link')!;
    expect(link.getAttribute('href')).toBe('/system?tab=logs');
    expect(link.textContent!.trim()).toBe('Full activity log →');
    expect(link.classList).toContain('sb-hit');
  });

  it('says loading before the first answer, with no link yet', () => {
    const { el } = mount([], null, ago(2), true);
    expect(text(el.querySelector('[role=status]')!)).toBe('Loading…');
    expect(el.querySelector('a.link')).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-activity-section.spec.ts
```

Expected: FAIL to compile: `LiveActivitySection` is not exported.

- [ ] **Step 3: Write the component**

In `shell/live/live-activity-section.ts`, add above the existing imports:

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
```

add `import { PanelError } from '../../ui/panel-error';` after the `ui/format` import, and append at the end of the file:

```ts
let nextId = 0;

/**
 * Activity -- v203 (spec v202 §4.4). The last events from /live, each with
 * its Berlin time and age, a tone and one line; every P&L line reads
 * "(paper, pre-cost)". A partial read says which sources failed, a failed
 * one says so with a retry, and a stopped bot reads "No scan since …".
 */
@Component({
  selector: 'sb-live-activity',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PanelError],
  template: `
    <section class="live-section" [attr.aria-labelledby]="headingId">
      <h2 class="title" [id]="headingId">Activity</h2>
      @switch (view().state) {
        @case ('loading') { <p class="muted" role="status">Loading…</p> }
        @case ('unavailable') { <sb-panel-error message="Activity unavailable" (retry)="retry.emit()" /> }
        @default {
          @if (view().scanWarning; as warning) { <p class="scan-warning warn" role="status">{{ warning }}</p> }
          @if (view().rows.length) {
            <ol class="events">
              @for (row of view().rows; track row.key) {
                <li [class]="'tone-' + row.tone">
                  <span class="dot" aria-hidden="true"></span>
                  <time>{{ row.time }}</time>
                  <span class="line">{{ row.text }}@if (row.pnl; as pnl) { · <span class="r">{{ pnl.r }}</span>@if (pnl.amount) {<span class="amt"> ({{ pnl.amount }})</span>}<span class="paper"> (paper, pre-cost)</span>}</span>
                </li>
              }
            </ol>
          }
          @if (view().quiet) { <p class="quiet">Nothing yet today</p> }
          @if (view().missing; as missing) { <p class="faint">{{ missing }}</p> }
        }
      }
      @if (view().state !== 'loading') {
        <a class="link sb-hit" routerLink="/system" [queryParams]="logParams">Full activity log →</a>
      }
    </section>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .title { margin: 0 0 var(--space-6); color: var(--text-muted); font-size: var(--text-micro); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    p { margin: 0 0 var(--space-4); font-size: var(--text-table); overflow-wrap: anywhere; }
    .events { display: flex; flex-direction: column; gap: var(--space-6); margin: 0 0 var(--space-6); padding: 0; list-style: none; }
    li { display: grid; grid-template-columns: auto 1fr; gap: 0 var(--space-6); align-items: baseline; min-width: 0; font-size: var(--text-table); }
    .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); grid-row: span 2; align-self: center; }
    time { color: var(--text-muted); font-variant-numeric: tabular-nums; }
    .line { grid-column: 2; min-width: 0; color: var(--text); overflow-wrap: anywhere; }
    .amt, .paper { color: var(--text-secondary); }
    .tone-info .dot { background: var(--accent); }
    .tone-positive .dot { background: var(--pos); }
    .tone-positive .r { color: var(--pos); }
    .tone-negative .dot { background: var(--neg); }
    .tone-negative .r { color: var(--neg); }
    .tone-warning .dot { background: var(--warn); }
    .muted, .quiet, .faint { color: var(--text-muted); }
    .faint { font-size: var(--text-micro); }
    .warn { color: var(--warn); }
    .link { display: inline-flex; align-items: center; min-height: var(--control-h); color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .link:hover { text-decoration: underline; }
  `,
})
export class LiveActivitySection {
  readonly events = input<readonly LiveEvent[]>([]);
  readonly meta = input<LiveEventsMeta | null>(null);
  readonly loading = input(false);
  readonly lastSuccess = input<string | null>(null);
  readonly now = input.required<Date>();
  readonly currency = input(DEFAULT_CURRENCY);
  readonly retry = output<void>();

  protected readonly headingId = `live-activity-${nextId++}`;
  protected readonly logParams = { tab: 'logs' };
  protected readonly view = computed(() => activityView(
    this.events(), this.meta(), this.loading(), this.lastSuccess(), this.now(), this.currency(),
  ));
}
```

The tone colours are today's `--accent`, `--pos`, `--neg`, `--warn` and `--text-muted` (no new colour). The amount and the paper label sit in `--text-secondary`, the neutral text colour the spec asks for beside the R. Each separating space sits inside a non-blank text node (` · `, ` (441 €)`, ` (paper, pre-cost)`): Angular drops whitespace-only text nodes between elements, so a bare space between two spans would vanish and the line would no longer read as `activityLine`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm --prefix <wt>/frontend test -- --watch=false --include src/app/shell/live/live-activity-section.spec.ts
```
```bash
npm --prefix <wt>/frontend run lint
```

Expected: PASS, lint clean. If the row test's `.line` text differs only in spacing around `·`, fix the template's whitespace, not the expectation: the line must read exactly as `activityLine`.

Complexity: the component has no branching code; the template's branches are V203-6's `activityView` state.

Layout: no screen renders this section until V203-7b mounts the dock (desktop) and V203-8b the sheet (tablet, phone). Their three-width audits cover it, so record in the report that the visual check is deferred to those tasks. Long lines wrap (`overflow-wrap: anywhere`), never scroll sideways.

- [ ] **Step 5: Commit**

```bash
git -C <wt> add frontend/src/app/shell/live/live-activity-section.ts frontend/src/app/shell/live/live-activity-section.spec.ts
git -C <wt> commit -m "feat(v203): the dock's Activity section

The last events with Berlin time and age, a tone and one line; the R in
its tone and the amount in neutral text; \"Activity unavailable\" with a
retry; the partial line after the rows; and the link to System -> Logs.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

