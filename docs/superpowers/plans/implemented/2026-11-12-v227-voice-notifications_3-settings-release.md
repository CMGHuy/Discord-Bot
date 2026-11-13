# v227 — Voice notifications, Part 3: Settings block, layout audit and release (V227-12..V227-15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v227 — Voice notifications: bomeo-capital.com speaks every simple-channel post](../specs/2026-11-12-v227-voice-notifications-design.md) (§ 4 Settings → Voice notifications; § 3 Unavailable "Settings says the same"; § Testing frontend; three widths)

Part 3 of the index's Parts table. Goal, architecture, **Global Constraints**,
**Parallelisation** and the task ledger live in the index:
[`2026-11-12-v227-voice-notifications_0-index.md`](2026-11-12-v227-voice-notifications_0-index.md).
Every task below implicitly carries those constraints. Work happens in the
worktree `.claude/worktrees/2026-11-12-v227-voice-notifications` (all paths
below are relative to it). Frontend runs are narrow:
`node frontend/scripts/ng-test.mjs frontend --include <spec>` (the spec path is
relative to `frontend/`). Never `cd frontend` (the repo hooks forbid it); use
`npm --prefix frontend ...`.

Repo rules these tasks lean on, on top of the ones Part 2's header lists
(effects flush on `TestBed.tick()`; `--hit-min` instead of a coarse-pointer
block; no `speechSynthesis` under jsdom, so specs provide `FakeSpeech` and
`fakeUtterance` through `SPEECH`/`UTTERANCE`):

- **Width queries use only the declared breakpoints** (`ui/breakpoint-guard.spec.ts`:
  640, 1024, 1440, 1920 and each minus one). The index note's "two columns
  ≥ 768 px" is therefore written as `@media (min-width: 640px)`: one column on
  phone (< 640), two on tablet (640–1023) and desktop, which is what spec §4
  asks for at the three audited widths (390 → one, 768 and 1440 → two).
- **A raw `<input>` outside `ui/` needs a `RAW_CONTROL_ALLOWLIST` entry with a
  comment** (`ui/primitives.spec.ts`); the rate slider is the first range
  input in the app, so V227-13 adds one entry (no slider primitive exists).
- **Radii are tokens or `50%`** (`primitives.spec.ts` radius rule); colours are
  tokens only; no `title=` (`title-usage.spec.ts`); styles live in a TS
  template literal, so no backticks inside them.
- **`sb-panel` is not user-collapsible** (its collapse is viewport-driven), so
  the "collapsible block" is a native `<details class="voice">` inside the
  panel, the same pattern as the tab's `<details class="import">`. The master
  switch stays outside the `<details>` so voice can be switched off without
  opening anything; the `<details>` starts **open** so the layout audit
  (which cannot click) measures every control inside it.

# Phase 7 — Settings block, audit and release

### Task V227-12: Settings block: master switch, family and kind switches

**Model:** sonnet — one standalone component on two existing services; copy, layout and tests are fixed below.

**Files:**
- Create: `frontend/src/app/workspaces/system/voice-settings.ts`
- Create: `frontend/src/app/workspaces/system/voice-settings.spec.ts`

(The ledger row's `settings-tab.ts` / `settings-tab.spec.ts` edits and the
per-kind previews moved to V227-12b, split from this task at the 20 KB cap.)

**Interfaces:**
- Consumes: `ApiClient.feedPostKinds(): Observable<FeedKindFamily[]>`, `FeedKindFamily {family; label; default_on; kinds: FeedKind[]}`, `FeedKind {kind; label; phrase; sample}` (V227-7, `frontend/src/app/api/models.ts`); `VoicePrefs.value()`, `.isKindOn(kind, family)`, `.setEnabled(on)`, `.setKind(kind, on)`, `.setKinds(kinds, on)`, `VOICE_STORAGE`, `VOICE_STORAGE_KEY` (V227-7); `SPEECH`, `UTTERANCE` (V227-8); `FakeSpeech`, `fakeUtterance` (V227-8, `frontend/src/app/voice/fake-speech.ts`); `Switch` (`sb-switch`: `label`, `checked`, `mixed`, `disabled`, `hint`, `(checkedChange)`; V227-11). Existing: `Panel` (`ui/layout.ts`), `Spinner` (`sb-spinner`, input `label`, `ui/spinner.ts`), `PanelError` (`sb-panel-error`, input `message`, output `retry`, `ui/panel-error.ts`).
- Produces (final; V227-12b and V227-13 extend the same files): `sb-voice-settings` (no inputs); class `VoiceSettings` with `families: Signal<FeedKindFamily[] | null>`, `enabled: Signal<boolean>`, `load(): void`, protected `prefs`, `rows`, `setFamily(family, on)`; exported `VOICE_OFF_REASON = 'Turn on voice to choose kinds'`, `spokenHint(phrase: string): string` (`Says: ${phrase}, <ticker>`), `familyRow(family: FeedKindFamily, isOn: (kind: string) => boolean): FamilyRow`, interfaces `KindRow`, `FamilyRow`. In the spec file: helpers `families()`, `mount(stored?, speech?)`, `loaded(stored?, speech?)`, `switchNamed(el, label)`, `click(fixture, button)` and the constant `KINDS_URL`, which V227-12b and V227-13 reuse.

What the block does (spec §4; copy exact, index Global Constraints):

- `<sb-panel heading="Voice notifications">`. First the master switch
  "Speak simple-channel posts" (`prefs.setEnabled`), always visible and always
  enabled; under it `VOICE_OFF_REASON` while the master is off.
- Then `<details class="voice" open>` with `<summary class="sb-hit">Kinds, voice and speed</summary>`.
  Inside: a spinner ("Loading kinds") until `feedPostKinds()` answers; on error
  an `sb-panel-error` whose Retry calls `load()` (the master switch keeps
  working either way); otherwise one group per family in the server's order.
- A family group: an `sb-switch` labelled with the family label, `checked`
  when every kind in it is on, `mixed` when some are; a change calls
  `setKinds(<every kind of the family>, value)`. Under it one row per kind: an
  `sb-switch` labelled with the Discord label, `hint` = `spokenHint(phrase)`.
- Master off: every family and kind switch is `disabled`.
- Layout: groups one column below 640 px, two from 640 px; kind rows indented
  under their family switch; labels wrap (the switch already wraps). Class
  names avoid the promoted composites (`head`, `row-link`, `note`, `chips`;
  `primitives.spec.ts`), hence `.reason`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/workspaces/system/voice-settings.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { FeedKindFamily } from '../../api/models';
import { FakeSpeech, fakeUtterance } from '../../voice/fake-speech';
import { VOICE_STORAGE, VOICE_STORAGE_KEY } from '../../voice/voice-prefs';
import { SPEECH, UTTERANCE } from '../../voice/voice-speaker';
import { VOICE_OFF_REASON, VoiceSettings, familyRow, spokenHint } from './voice-settings';

const KINDS_URL = '/api/v1/feed-posts/kinds';

function families(): FeedKindFamily[] {
  return [
    {
      family: 'ENTRY', label: 'Entry', default_on: true,
      kinds: [
        { kind: 'FILLED', label: 'FILLED', phrase: 'Order filled', sample: 'Order filled, AAPL' },
        { kind: 'ENTRY_TRIGGERED', label: 'ENTRY TRIGGERED', phrase: 'Entry triggered', sample: 'Entry triggered, AAPL' },
      ],
    },
    {
      family: 'WATCH', label: 'Watch', default_on: false,
      kinds: [
        { kind: 'NEAR_STOP', label: 'NEAR STOP', phrase: 'Near stop', sample: 'Near stop, AAPL' },
        { kind: 'NEAR_TP', label: 'NEAR TARGET', phrase: 'Near target', sample: 'Near target, AAPL' },
      ],
    },
  ];
}

function mount(stored: string | null = null, speech: FakeSpeech | null = new FakeSpeech()) {
  const map = new Map<string, string>();
  if (stored !== null) map.set(VOICE_STORAGE_KEY, stored);
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: SPEECH, useValue: speech },
      { provide: UTTERANCE, useValue: fakeUtterance },
      {
        provide: VOICE_STORAGE,
        useValue: {
          get: (key: string) => map.get(key) ?? null,
          set: (key: string, value: string) => {
            map.set(key, value);
          },
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(VoiceSettings);
  fixture.detectChanges();
  const backend = TestBed.inject(HttpTestingController);
  const el = fixture.nativeElement as HTMLElement;
  const saved = () => JSON.parse(map.get(VOICE_STORAGE_KEY) ?? '{}');
  return { fixture, backend, el, speech, saved };
}

async function loaded(stored: string | null = null, speech: FakeSpeech | null = new FakeSpeech()) {
  const ctx = mount(stored, speech);
  ctx.backend.expectOne(KINDS_URL).flush({ families: families() });
  await ctx.fixture.whenStable();
  ctx.fixture.detectChanges();
  return ctx;
}

function switchNamed(el: HTMLElement, label: string): HTMLButtonElement {
  const found = [...el.querySelectorAll<HTMLButtonElement>('button[role="switch"]')]
    .find((button) => button.textContent!.trim() === label);
  if (!found) throw new Error(`no switch labelled ${label}`);
  return found;
}

function click(fixture: { detectChanges(): void }, button: HTMLButtonElement): void {
  button.click();
  fixture.detectChanges();
}

describe('VoiceSettings (v227)', () => {
  it('renders the block heading and the master switch, on by default', async () => {
    const { el } = await loaded();
    expect(el.querySelector('h2')!.textContent!.trim()).toBe('Voice notifications');
    expect(switchNamed(el, 'Speak simple-channel posts').getAttribute('aria-checked')).toBe('true');
    expect(el.textContent).not.toContain(VOICE_OFF_REASON);
    expect(el.querySelector('details.voice')!.hasAttribute('open')).toBe(true);
  });

  it('starts every family on except Watch', async () => {
    const { el } = await loaded();
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('true');
    expect(switchNamed(el, 'FILLED').getAttribute('aria-checked')).toBe('true');
    expect(switchNamed(el, 'Watch').getAttribute('aria-checked')).toBe('false');
    expect(switchNamed(el, 'NEAR STOP').getAttribute('aria-checked')).toBe('false');
  });

  it('master off saves, greys every switch below it, and says why', async () => {
    const { el, fixture, saved } = await loaded();
    click(fixture, switchNamed(el, 'Speak simple-channel posts'));
    expect(saved().enabled).toBe(false);
    expect(switchNamed(el, 'Speak simple-channel posts').disabled).toBe(false);
    for (const label of ['Entry', 'FILLED', 'ENTRY TRIGGERED', 'Watch', 'NEAR STOP', 'NEAR TARGET']) {
      expect(switchNamed(el, label).disabled).toBe(true);
    }
    expect(el.textContent).toContain(VOICE_OFF_REASON);
  });

  it('a kind switch saves just that kind and leaves its family mixed', async () => {
    const { el, fixture, saved } = await loaded();
    click(fixture, switchNamed(el, 'FILLED'));
    expect(saved().kinds).toEqual({ FILLED: false });
    expect(switchNamed(el, 'FILLED').getAttribute('aria-checked')).toBe('false');
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('mixed');
  });

  it('a mixed family switch turns the whole family on in one save', async () => {
    const { el, fixture, saved } = await loaded(JSON.stringify({ kinds: { FILLED: false } }));
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('mixed');
    click(fixture, switchNamed(el, 'Entry'));
    expect(saved().kinds).toEqual({ FILLED: true, ENTRY_TRIGGERED: true });
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('true');
  });

  it('the Watch switch turns both near-stop and near-target on', async () => {
    const { el, fixture, saved } = await loaded();
    click(fixture, switchNamed(el, 'Watch'));
    expect(saved().kinds).toEqual({ NEAR_STOP: true, NEAR_TP: true });
    expect(switchNamed(el, 'NEAR TARGET').getAttribute('aria-checked')).toBe('true');
  });

  it('shows under each kind what will be spoken', async () => {
    const { el } = await loaded();
    const hintId = switchNamed(el, 'FILLED').getAttribute('aria-describedby')!;
    expect(el.querySelector(`#${hintId}`)!.textContent!.trim()).toBe('Says: Order filled, <ticker>');
  });

  it('falls back to the defaults on a garbled store', async () => {
    const { el } = await loaded('{not json');
    expect(switchNamed(el, 'Speak simple-channel posts').getAttribute('aria-checked')).toBe('true');
    expect(switchNamed(el, 'Watch').getAttribute('aria-checked')).toBe('false');
    expect(switchNamed(el, 'Entry').getAttribute('aria-checked')).toBe('true');
  });

  it('keeps the master switch working while the kinds load and after they fail', async () => {
    const { el, fixture, backend, saved } = mount();
    expect(el.querySelector('sb-spinner')).toBeTruthy();
    backend.expectOne(KINDS_URL).flush({ error: { code: 'unavailable', message: 'x' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('sb-panel-error')).toBeTruthy();
    expect(el.querySelector('sb-spinner')).toBeNull();
    click(fixture, switchNamed(el, 'Speak simple-channel posts'));
    expect(saved().enabled).toBe(false);
    click(fixture, el.querySelector<HTMLButtonElement>('sb-panel-error button')!);
    backend.expectOne(KINDS_URL).flush({ families: families() });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('sb-panel-error')).toBeNull();
    expect(switchNamed(el, 'FILLED')).toBeTruthy();
  });
});

describe('familyRow (v227)', () => {
  const entry = families()[0];

  it('is all on, mixed or all off from the kind flags', () => {
    expect(familyRow(entry, () => true)).toMatchObject({ allOn: true, mixed: false });
    expect(familyRow(entry, (kind) => kind === 'FILLED')).toMatchObject({ allOn: false, mixed: true });
    expect(familyRow(entry, () => false)).toMatchObject({ allOn: false, mixed: false });
  });

  it('is neither on nor mixed for a family with no kinds', () => {
    expect(familyRow({ ...entry, kinds: [] }, () => true)).toMatchObject({ allOn: false, mixed: false, kinds: [] });
  });

  it('carries the spoken hint for every kind', () => {
    expect(familyRow(entry, () => true).kinds.map((kind) => kind.hint)).toEqual([
      'Says: Order filled, <ticker>',
      'Says: Entry triggered, <ticker>',
    ]);
    expect(spokenHint('Near stop')).toBe('Says: Near stop, <ticker>');
  });
});

describe('VoiceSettings layout (v227)', () => {
  const source = readFileSync(join(process.cwd(), 'src/app/workspaces/system/voice-settings.ts'), 'utf8');

  it('stacks the families on a phone and sets two columns from the 640px breakpoint', () => {
    expect(source).toMatch(/\.families \{[^}]*grid-template-columns: minmax\(0, 1fr\);/);
    expect(source).toMatch(/@media \(min-width: 640px\) \{\s*\.families \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
  });

  it('never truncates a label and explains nothing through title', () => {
    expect(source).not.toMatch(/text-overflow|white-space: nowrap/);
    expect(source).not.toMatch(/\stitle=/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/system/voice-settings.spec.ts
```

Expected: FAIL — `Cannot find module './voice-settings'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/workspaces/system/voice-settings.ts`:

```ts
import { ChangeDetectionStrategy, Component, DestroyRef, Signal, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiClient } from '../../api/api-client';
import { FeedKind, FeedKindFamily } from '../../api/models';
import { Panel } from '../../ui/layout';
import { PanelError } from '../../ui/panel-error';
import { Spinner } from '../../ui/spinner';
import { Switch } from '../../ui/switch';
import { VoicePrefs } from '../../voice/voice-prefs';

export const VOICE_OFF_REASON = 'Turn on voice to choose kinds';

/** The plain-words line under a kind: what the site will say for it. */
export function spokenHint(phrase: string): string {
  return `Says: ${phrase}, <ticker>`;
}

export interface KindRow extends FeedKind {
  on: boolean;
  hint: string;
}

export interface FamilyRow {
  family: string;
  label: string;
  kinds: KindRow[];
  /** Every kind on (an empty family is never "all on"). */
  allOn: boolean;
  /** Some kinds on, some off: the family switch reads aria-checked="mixed". */
  mixed: boolean;
}

/** One family's switches from the stored flags; pure, so it is tested alone. */
export function familyRow(family: FeedKindFamily, isOn: (kind: string) => boolean): FamilyRow {
  const kinds = family.kinds.map((kind) => ({ ...kind, on: isOn(kind.kind), hint: spokenHint(kind.phrase) }));
  const onCount = kinds.filter((kind) => kind.on).length;
  return {
    family: family.family,
    label: family.label,
    kinds,
    allOn: kinds.length > 0 && onCount === kinds.length,
    mixed: onCount > 0 && onCount < kinds.length,
  };
}

/**
 * System → Settings → Voice notifications (spec v227 §4).
 *
 * Per-browser choices only (VoicePrefs, localStorage): nothing here reads or
 * writes the /system/settings payload, which is why the tab mounts this block
 * outside its sb-async -- it works while that payload loads or fails.
 *
 * The kinds come from GET /feed-posts/kinds, so a kind added to the server's
 * registry appears here with no frontend change. The master switch sits
 * outside the details element so voice can be switched off without opening
 * anything; the details start open so a first visit shows every choice.
 */
@Component({
  selector: 'sb-voice-settings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Switch, Spinner, PanelError],
  template: `
    <sb-panel heading="Voice notifications">
      <div class="master">
        <sb-switch label="Speak simple-channel posts" [checked]="enabled()" (checkedChange)="prefs.setEnabled($event)" />
        @if (!enabled()) {
          <p class="reason">{{ offReason }}</p>
        }
      </div>
      <details class="voice" open>
        <summary class="sb-hit">Kinds, voice and speed</summary>
        @if (loadError()) {
          <sb-panel-error message="voice kinds" (retry)="load()" />
        } @else if (families() === null) {
          <sb-spinner label="Loading kinds" />
        } @else {
          <div class="families">
            @for (family of rows(); track family.family) {
              <section class="family" role="group" [attr.aria-label]="family.label">
                <sb-switch
                  [label]="family.label"
                  [checked]="family.allOn"
                  [mixed]="family.mixed"
                  [disabled]="!enabled()"
                  (checkedChange)="setFamily(family, $event)"
                />
                <ul class="kinds">
                  @for (kind of family.kinds; track kind.kind) {
                    <li class="kind">
                      <sb-switch
                        [label]="kind.label"
                        [checked]="kind.on"
                        [hint]="kind.hint"
                        [disabled]="!enabled()"
                        (checkedChange)="prefs.setKind(kind.kind, $event)"
                      />
                    </li>
                  }
                </ul>
              </section>
            }
          </div>
        }
      </details>
    </sb-panel>
  `,
  styles: `
    /* No backticks in here: these styles live in a TS template literal. */
    :host { display: block; min-width: 0; }
    .master { display: flex; flex-direction: column; gap: var(--space-4); }
    .reason { margin: 0; color: var(--text-secondary); font-size: var(--text-table); overflow-wrap: anywhere; }
    .voice { margin-top: var(--space-14); font-size: var(--text-table); }
    summary { color: var(--text-secondary); cursor: pointer; }
    .families { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); margin-top: var(--space-10); }
    @media (min-width: 640px) {
      .families { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .family { min-width: 0; }
    .kinds { display: grid; gap: var(--space-4); margin: var(--space-4) 0 0; padding: 0 0 0 var(--space-14); list-style: none; }
    .kind { display: flex; align-items: flex-start; gap: var(--space-8); min-width: 0; }
    .kind sb-switch { flex: 1 1 auto; min-width: 0; }
  `,
})
export class VoiceSettings {
  protected readonly prefs = inject(VoicePrefs);
  private readonly api = inject(ApiClient);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly offReason = VOICE_OFF_REASON;

  private readonly kindList = signal<FeedKindFamily[] | null>(null);
  protected readonly loadError = signal(false);

  readonly families: Signal<FeedKindFamily[] | null> = this.kindList.asReadonly();
  readonly enabled = computed(() => this.prefs.value().enabled);

  /** isKindOn reads the prefs signal, so a toggle recomputes the rows. */
  protected readonly rows = computed(() =>
    (this.kindList() ?? []).map((family) => familyRow(family, (kind) => this.prefs.isKindOn(kind, family.family))),
  );

  constructor() {
    this.load();
  }

  /** Fetch the kinds; Retry on the error line calls this again. */
  load(): void {
    this.loadError.set(false);
    this.api
      .feedPostKinds()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (families) => this.kindList.set(families),
        error: () => this.loadError.set(true),
      });
  }

  protected setFamily(family: FamilyRow, on: boolean): void {
    this.prefs.setKinds(family.kinds.map((kind) => kind.kind), on);
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/system/voice-settings.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/hit-area.spec.ts
```

Expected: PASS, `0 failed`. If `primitives.spec.ts` flags a class name, it is
a promoted composite: rename the class, never add an allowlist entry.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system/voice-settings.ts frontend/src/app/workspaces/system/voice-settings.spec.ts
git commit -m "feat(ui): v227 Settings voice block, master, family and kind switches (V227-12)"
```

### Task V227-12b: Settings block: per-kind previews, the no-voice note, mounted in the Settings tab

**Model:** sonnet — additive edits to the V227-12 component plus a two-line mount in the Settings tab; every change is shown below.

Split from V227-12 at the 20 KB task cap (never compressed). Runs after
V227-12 (same files).

**Files:**
- Modify: `frontend/src/app/workspaces/system/voice-settings.ts` (created by V227-12)
- Modify: `frontend/src/app/workspaces/system/voice-settings.spec.ts` (created by V227-12)
- Modify: `frontend/src/app/workspaces/system/settings-tab.ts` (import; `imports:` line 36; template between `</sb-async>` (line 310) and `<sb-panel heading="Recent changes">` (line 314))
- Modify: `frontend/src/app/workspaces/system/settings-tab.spec.ts` (one new `describe` at the end)

**Interfaces:**
- Consumes: V227-12's `VoiceSettings` (`prefs`, `enabled`, `rows`, the `.kind` row) and its spec helpers `loaded`, `switchNamed`, `click`; `VoiceSpeaker.state()`, `VoiceSpeaker.preview(text)` (V227-8/8b); `FakeSpeech.texts()` (V227-8); `Button` (`button[sb-button]`, `ui/button.ts`); the settings spec's `seed()` (`settings-tab.spec.ts:26`).
- Produces (final; V227-13 consumes `speaker`, `unavailable`, `canSpeak`): `NO_VOICE_NOTE = 'No voice on this browser'` (exported); on `VoiceSettings`: protected `speaker: VoiceSpeaker`, `unavailable: Signal<boolean>` (`state() === 'unavailable'`), `canSpeak: Signal<boolean>` (`enabled() && !unavailable()`). The Settings tab renders `<sb-voice-settings />` outside its `<sb-async>`.

Rules (spec §3 "Unavailable … Settings says the same"; §4 per-kind ▶ preview):

- Each kind row gains a `▶` `sb-button` (`variant="ghost"`, class `preview`,
  `aria-label` `Preview <label>`) calling `speaker.preview(sample)`. A preview
  is a tap, so it speaks even while the chip is still `locked` and never
  unlocks it (V227-8b). It is disabled when `canSpeak()` is false.
- Under the master switch, `NO_VOICE_NOTE` (with `role="status"`) replaces the
  off-reason line when the browser has no speech at all.
- The preview is at least `--hit-min` wide (44 px on touch and below 1024 px).
- The Settings tab mounts the block **outside** `<sb-async>` (index
  Architecture): it never waits on, or errors with, the `/system/settings`
  payload.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/system/voice-settings.spec.ts`, change the
`./voice-settings` import to

```ts
import { NO_VOICE_NOTE, VOICE_OFF_REASON, VoiceSettings, familyRow, spokenHint } from './voice-settings';
```

and append at the end of the file:

```ts
describe('VoiceSettings previews and the no-voice note (v227)', () => {
  it('previews a kind sample on tap, without unlocking the chip', async () => {
    const speech = new FakeSpeech();
    const { el } = await loaded(null, speech);
    const preview = el.querySelector<HTMLButtonElement>('button[aria-label="Preview FILLED"]')!;
    expect(preview.disabled).toBe(false);
    expect(preview.textContent!.trim()).toBe('▶');
    preview.click();
    expect(speech.texts()).toEqual(['Order filled, AAPL']);
    expect(TestBed.inject(VoiceSpeaker).state()).toBe('locked');
  });

  it('has one preview per kind, all disabled while the master is off', async () => {
    const { el, fixture } = await loaded();
    const previews = () => [...el.querySelectorAll<HTMLButtonElement>('button.preview')];
    expect(previews().length).toBe(4);
    click(fixture, switchNamed(el, 'Speak simple-channel posts'));
    expect(previews().every((button) => button.disabled)).toBe(true);
  });

  it('says so when this browser has no voice, and disables the previews', async () => {
    const { el } = await loaded(null, null);
    const status = el.querySelector('.master [role="status"]')!;
    expect(status.textContent!.trim()).toBe(NO_VOICE_NOTE);
    expect(el.textContent).not.toContain(VOICE_OFF_REASON);
    const previews = [...el.querySelectorAll<HTMLButtonElement>('button.preview')];
    expect(previews.length).toBe(4);
    expect(previews.every((button) => button.disabled)).toBe(true);
  });

  it('gives the preview a full hit area', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/system/voice-settings.ts'), 'utf8');
    expect(source).toMatch(/\.preview \{[^}]*min-width: var\(--hit-min\);/);
  });
});
```

and add `VoiceSpeaker` to the `../../voice/voice-speaker` import:

```ts
import { SPEECH, UTTERANCE, VoiceSpeaker } from '../../voice/voice-speaker';
```

Append to `frontend/src/app/workspaces/system/settings-tab.spec.ts`
(`readFileSync`, `join` and `seed()` already exist at the top of that file):

```ts
describe('SettingsTab voice block (v227)', () => {
  it('renders the voice block while the settings payload is still loading', () => {
    const { fixture } = seed();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
    expect(el.querySelector('sb-voice-settings')).toBeTruthy();
  });

  it('keeps the voice block outside sb-async, before Recent changes', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/system/settings-tab.ts'), 'utf8');
    const asyncEnd = source.indexOf('</sb-async>');
    const voice = source.indexOf('<sb-voice-settings />');
    const recent = source.indexOf('<sb-panel heading="Recent changes">');
    expect(asyncEnd).toBeGreaterThan(0);
    expect(voice).toBeGreaterThan(asyncEnd);
    expect(voice).toBeLessThan(recent);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/system/voice-settings.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts
```

Expected: FAIL — `NO_VOICE_NOTE` is not exported, no `button.preview` exists,
and the settings tab renders no `sb-voice-settings`.

- [ ] **Step 3: Write the implementation**

`frontend/src/app/workspaces/system/voice-settings.ts`:

1. Imports: add

```ts
import { Button } from '../../ui/button';
import { VoiceSpeaker } from '../../voice/voice-speaker';
```

2. Under `VOICE_OFF_REASON`:

```ts
export const NO_VOICE_NOTE = 'No voice on this browser';
```

3. `imports: [Panel, Switch, Spinner, PanelError]` becomes
   `imports: [Panel, Switch, Button, Spinner, PanelError]`.

4. In the template, replace the master's reason block

```html
        @if (!enabled()) {
          <p class="reason">{{ offReason }}</p>
        }
```

with

```html
        @if (unavailable()) {
          <p class="reason" role="status">{{ noVoice }}</p>
        } @else if (!enabled()) {
          <p class="reason">{{ offReason }}</p>
        }
```

5. In the kind row, after the kind's `<sb-switch … />` and before `</li>`:

```html
                      <button
                        sb-button
                        variant="ghost"
                        type="button"
                        class="preview"
                        [attr.aria-label]="'Preview ' + kind.label"
                        [disabled]="!canSpeak()"
                        (click)="speaker.preview(kind.sample)"
                      >▶</button>
```

6. Styles: after `.kind sb-switch { … }` add

```css
    .preview { flex: none; min-width: var(--hit-min); }
```

7. Class body: after `protected readonly prefs = inject(VoicePrefs);` add
   `protected readonly speaker = inject(VoiceSpeaker);`, after
   `protected readonly offReason = VOICE_OFF_REASON;` add
   `protected readonly noVoice = NO_VOICE_NOTE;`, and after `enabled`:

```ts
  readonly unavailable = computed(() => this.speaker.state() === 'unavailable');
  /** Previews and Test voice: the master is on and the browser can speak. */
  readonly canSpeak = computed(() => this.enabled() && !this.unavailable());
```

`frontend/src/app/workspaces/system/settings-tab.ts`: add the import

```ts
import { VoiceSettings } from './voice-settings';
```

extend line 36 to

```ts
  imports: [Panel, Button, TextInput, Select, Checkbox, ControlRow, Async, Hint, VoiceSettings],
```

and in the template, between `</sb-async>` and the `<!-- audit, export, import -->` comment:

```html
    </sb-async>

    <!-- v227: per-browser voice choices. Outside sb-async on purpose: they
         never touch the /system/settings payload, so they render (and work)
         while it loads or fails. -->
    <sb-voice-settings />

    <!-- audit, export, import ------------------------------------------ -->
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/system/voice-settings.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/workspaces/system/system.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/title-usage.spec.ts
```

Expected: PASS, `0 failed`. Under jsdom the tab's real `SPEECH` resolves to
`null`, so the mounted block shows the no-voice note there; that is correct.
If a `system.spec.ts` test calls `HttpTestingController.verify()` and now sees
the unmatched `/api/v1/feed-posts/kinds` request, flush it in that test with
`{ families: [] }`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system/voice-settings.ts frontend/src/app/workspaces/system/voice-settings.spec.ts
git commit -m "feat(ui): v227 voice block previews each kind and names a voiceless browser (V227-12b)"
git add frontend/src/app/workspaces/system/settings-tab.ts frontend/src/app/workspaces/system/settings-tab.spec.ts
git commit -m "feat(ui): v227 Settings tab mounts the voice block outside sb-async (V227-12b)"
```

### Task V227-13: Settings block: voice picker, rate slider, Test voice

**Model:** sonnet — three controls added to the V227-12 component, with the copy, ranges and fallbacks fixed by the spec and the code below.

Runs after V227-12b (same files) and after V227-10 (both edit
`frontend/src/app/ui/primitives.spec.ts`, different allowlists).

**Files:**
- Modify: `frontend/src/app/workspaces/system/voice-settings.ts` (created by V227-12)
- Modify: `frontend/src/app/workspaces/system/voice-settings.spec.ts` (created by V227-12)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (`RAW_CONTROL_ALLOWLIST`, one entry; joins this task beyond its ledger row)

**Interfaces:**
- Consumes: `VoiceSettings` with `prefs`, `speaker`, `enabled`, `canSpeak`, `families` (V227-12, V227-12b) and the spec helpers `loaded`, `click`, `switchNamed`, `families()` (V227-12); `VoicePrefs.setVoice(name: string | null)`, `.setRate(rate: number)`, `RATE_MIN`, `RATE_MAX`, `RATE_STEP` (V227-7); `VoiceSpeaker.voices(): string[] | null` (null = still loading), `.preview(text)` (V227-8/8b); `FakeSpeech.setVoices(names)`, `.texts()` (V227-8); `Select` (`sb-select`: model `value`, inputs `options: SelectOption[]`, `label`, `disabled`; `ui/form-controls.ts:23`), `SelectOption {value; label}`.
- Produces (final): exported `SYSTEM_DEFAULT_VOICE = 'System default'`, `LOADING_VOICES = 'Loading voices…'`, `MISSING_VOICE_NOTE`, `TEST_VOICE_FALLBACK = 'New long alert, AAPL, buy at 187.50'`, `voiceOptions(voices: string[] | null): SelectOption[]`, `rateText(rate: number): string` (`1.00×`), `testVoiceSample(families: FeedKindFamily[] | null): string`.

Rules (spec §4; index notes V227-13; copy exact):

- **Voice picker** `sb-select` labelled "Voice": options "System default"
  (value `''`) then every device voice by name. While `voices()` is `null` it
  shows the single option "Loading voices…" and is disabled. A stored voice
  missing from a loaded list shows "System default" and the one-line note
  `MISSING_VOICE_NOTE`; the stored name is kept (another device may have it).
  Choosing "System default" stores `null`.
- **Rate** `<input type="range">` 0.8–1.4, step 0.05, labelled "Rate", the
  value printed beside it in an `<output>` as `1.00×`; the thumb is
  `--hit-min` square (44 px on touch and below 1024 px through `tokens.css`).
- **Test voice** `sb-button` speaks `testVoiceSample(families())`: the
  `SETUP_SIMPLE` sample from the kinds list, else `TEST_VOICE_FALLBACK`
  (works even when the kinds failed to load).
- Picker, slider and Test voice sit inside the `<details>`, after the families,
  outside the loading/error branch. The slider is disabled with the master
  off; the picker and Test voice also when the browser has no speech
  (`canSpeak()` false).
- The range input is the app's first: a `RAW_CONTROL_ALLOWLIST` entry with its
  reason, no new primitive.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/workspaces/system/voice-settings.spec.ts`, extend the
`./voice-settings` import to

```ts
import {
  LOADING_VOICES, MISSING_VOICE_NOTE, NO_VOICE_NOTE, SYSTEM_DEFAULT_VOICE, TEST_VOICE_FALLBACK, VOICE_OFF_REASON,
  VoiceSettings, familyRow, rateText, spokenHint, testVoiceSample, voiceOptions,
} from './voice-settings';
```

and append at the end of the file:

```ts
describe('VoiceSettings voice, rate and Test voice (v227)', () => {
  function picker(el: HTMLElement): HTMLSelectElement {
    return el.querySelector<HTMLSelectElement>('sb-select select')!;
  }
  function optionTexts(el: HTMLElement): string[] {
    return [...picker(el).options].map((option) => option.textContent!.trim());
  }

  it('shows Loading voices… in a disabled picker until the browser lists its voices', async () => {
    const speech = new FakeSpeech();
    const { el, fixture } = await loaded(null, speech);
    expect(optionTexts(el)).toEqual([LOADING_VOICES]);
    expect(picker(el).disabled).toBe(true);
    speech.setVoices(['Alice', 'Bob']);
    fixture.detectChanges();
    expect(optionTexts(el)).toEqual([SYSTEM_DEFAULT_VOICE, 'Alice', 'Bob']);
    expect(picker(el).disabled).toBe(false);
  });

  it('saves the chosen voice, and System default saves none', async () => {
    const speech = new FakeSpeech();
    const { el, fixture, saved } = await loaded(null, speech);
    speech.setVoices(['Alice', 'Bob']);
    fixture.detectChanges();
    picker(el).value = 'Bob';
    picker(el).dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(saved().voice).toBe('Bob');
    picker(el).value = '';
    picker(el).dispatchEvent(new Event('change'));
    expect(saved().voice).toBeNull();
  });

  it('falls back to System default with a note when the saved voice is not on this device', async () => {
    const speech = new FakeSpeech();
    const { el, fixture, saved } = await loaded(JSON.stringify({ voice: 'Zed' }), speech);
    expect(el.textContent).not.toContain(MISSING_VOICE_NOTE);
    speech.setVoices(['Alice']);
    fixture.detectChanges();
    expect(el.textContent).toContain(MISSING_VOICE_NOTE);
    expect(picker(el).value).toBe('');
    expect(saved().voice).toBe('Zed');
  });

  it('offers a 0.8 to 1.4 rate in 0.05 steps, prints it and saves it', async () => {
    const { el, fixture, saved } = await loaded();
    const slider = el.querySelector<HTMLInputElement>('input[type="range"]')!;
    expect([slider.min, slider.max, slider.step]).toEqual(['0.8', '1.4', '0.05']);
    expect(el.querySelector('.rate output')!.textContent!.trim()).toBe('1.00×');
    slider.value = '1.25';
    slider.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    // jsdom step-aligns a range value in floating point: compare closely.
    expect(saved().rate).toBeCloseTo(1.25, 5);
    expect(el.querySelector('.rate output')!.textContent!.trim()).toBe('1.25×');
  });

  it('Test voice speaks a sample new-alert headline, even before unlocking', async () => {
    const speech = new FakeSpeech();
    const { el } = await loaded(null, speech);
    const button = [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent!.trim() === 'Test voice')!;
    button.click();
    expect(speech.texts()).toEqual([TEST_VOICE_FALLBACK]);
  });

  it('master off disables the picker, the slider and Test voice', async () => {
    const speech = new FakeSpeech();
    const { el, fixture } = await loaded(null, speech);
    speech.setVoices(['Alice']);
    click(fixture, switchNamed(el, 'Speak simple-channel posts'));
    expect(picker(el).disabled).toBe(true);
    expect(el.querySelector<HTMLInputElement>('input[type="range"]')!.disabled).toBe(true);
    const button = [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent!.trim() === 'Test voice')!;
    expect(button.disabled).toBe(true);
  });

  it('keeps Test voice and the slider when the kinds fail to load', async () => {
    const { el, fixture, backend } = mount();
    backend.expectOne(KINDS_URL).flush({ error: { code: 'unavailable', message: 'x' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('input[type="range"]')).toBeTruthy();
    expect([...el.querySelectorAll('button')].some((b) => b.textContent!.trim() === 'Test voice')).toBe(true);
  });

  it('builds the options, the printed rate and the sample', () => {
    expect(voiceOptions(null)).toEqual([{ value: '', label: LOADING_VOICES }]);
    expect(voiceOptions(['A'])).toEqual([{ value: '', label: SYSTEM_DEFAULT_VOICE }, { value: 'A', label: 'A' }]);
    expect(rateText(1)).toBe('1.00×');
    expect(rateText(0.85)).toBe('0.85×');
    expect(testVoiceSample(null)).toBe(TEST_VOICE_FALLBACK);
    expect(testVoiceSample(families())).toBe(TEST_VOICE_FALLBACK);
    const withSetup = [{
      family: 'NEW_SETUP', label: 'New setup', default_on: true,
      kinds: [{ kind: 'SETUP_SIMPLE', label: 'SETUP', phrase: 'New alert', sample: 'New short alert, TSLA, sell at 250.00' }],
    }];
    expect(testVoiceSample(withSetup)).toBe('New short alert, TSLA, sell at 250.00');
    expect(NO_VOICE_NOTE).toBe('No voice on this browser');
  });

  it('sizes the slider thumb by --hit-min in both engines', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/workspaces/system/voice-settings.ts'), 'utf8');
    expect(source).toMatch(/::-webkit-slider-thumb \{[^}]*width: var\(--hit-min\);[^}]*height: var\(--hit-min\);/);
    expect(source).toMatch(/::-moz-range-thumb \{[^}]*width: var\(--hit-min\);[^}]*height: var\(--hit-min\);/);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/system/voice-settings.spec.ts
```

Expected: FAIL — the new names are not exported and no `sb-select` / range input exists.

- [ ] **Step 3: Write the implementation**

`frontend/src/app/workspaces/system/voice-settings.ts`:

1. Imports: add

```ts
import { Select, SelectOption } from '../../ui/form-controls';
import { RATE_MAX, RATE_MIN, RATE_STEP } from '../../voice/voice-prefs';
```

(merge `RATE_*` into the existing `VoicePrefs` import line), and
`imports: [Panel, Switch, Button, Spinner, PanelError]` becomes
`imports: [Panel, Switch, Button, Spinner, PanelError, Select]`.

2. Under `NO_VOICE_NOTE`:

```ts
export const SYSTEM_DEFAULT_VOICE = 'System default';
export const LOADING_VOICES = 'Loading voices…';
export const MISSING_VOICE_NOTE = "Your saved voice isn't on this device; using the system default.";
export const TEST_VOICE_FALLBACK = 'New long alert, AAPL, buy at 187.50';

/** The picker's options: one loading row until the browser lists its voices. */
export function voiceOptions(voices: string[] | null): SelectOption[] {
  if (voices === null) return [{ value: '', label: LOADING_VOICES }];
  return [{ value: '', label: SYSTEM_DEFAULT_VOICE }, ...voices.map((name) => ({ value: name, label: name }))];
}

export function rateText(rate: number): string {
  return `${rate.toFixed(2)}×`;
}

/** Test voice says the server's own new-alert sample, else a fixed one. */
export function testVoiceSample(families: FeedKindFamily[] | null): string {
  for (const family of families ?? []) {
    const setup = family.kinds.find((kind) => kind.kind === 'SETUP_SIMPLE');
    if (setup?.sample) return setup.sample;
  }
  return TEST_VOICE_FALLBACK;
}
```

3. Template: inside `<details class="voice" open>`, after the closing `}` of
   the `@if (loadError()) … @else …` chain and before `</details>`:

```html
        <div class="voice-controls">
          <sb-select
            label="Voice"
            [options]="voiceList()"
            [value]="selectedVoice()"
            [disabled]="!canSpeak() || speaker.voices() === null"
            (valueChange)="prefs.setVoice($event || null)"
          />
          <label class="rate">
            <span class="sb-label">Rate</span>
            <span class="rate-row">
              <input
                type="range"
                [min]="rateMin"
                [max]="rateMax"
                [step]="rateStep"
                [value]="rate()"
                [disabled]="!enabled()"
                (input)="onRate($event)"
              />
              <output>{{ rateLabel() }}</output>
            </span>
          </label>
          <button sb-button variant="secondary" type="button" [disabled]="!canSpeak()" (click)="testVoice()">
            Test voice
          </button>
          @if (missingVoice()) {
            <p class="reason missing">{{ missingVoiceNote }}</p>
          }
        </div>
```

4. Styles, appended:

```css
    .voice-controls { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--space-10) var(--space-14); margin-top: var(--space-14); }
    .missing { flex-basis: 100%; }
    .rate { display: inline-flex; flex: 1 1 220px; flex-direction: column; gap: var(--space-4); min-width: 0; }
    .rate-row { display: flex; align-items: center; gap: var(--space-8); }
    .rate input {
      flex: 1 1 auto;
      min-width: 0;
      height: var(--hit-min);
      margin: 0;
      background: transparent;
      -webkit-appearance: none;
      appearance: none;
    }
    .rate input:disabled { opacity: 0.45; }
    .rate input::-webkit-slider-runnable-track { height: 4px; border-radius: var(--chip-radius); background: var(--border-strong); }
    .rate input::-webkit-slider-thumb { -webkit-appearance: none; width: var(--hit-min); height: var(--hit-min); margin-top: calc(2px - var(--hit-min) / 2); border-radius: 50%; background: var(--accent); }
    .rate input::-moz-range-track { height: 4px; border-radius: var(--chip-radius); background: var(--border-strong); }
    .rate input::-moz-range-thumb { width: var(--hit-min); height: var(--hit-min); border: 0; border-radius: 50%; background: var(--accent); }
    .rate output { min-width: 5ch; color: var(--text); font-variant-numeric: tabular-nums; }
```

5. Class body, after `canSpeak`:

```ts
  protected readonly rateMin = RATE_MIN;
  protected readonly rateMax = RATE_MAX;
  protected readonly rateStep = RATE_STEP;
  protected readonly missingVoiceNote = MISSING_VOICE_NOTE;

  protected readonly voiceList = computed(() => voiceOptions(this.speaker.voices()));
  /** A stored voice this device's loaded list does not have. */
  protected readonly missingVoice = computed(() => {
    const stored = this.prefs.value().voice;
    const voices = this.speaker.voices();
    return stored !== null && voices !== null && !voices.includes(stored);
  });
  protected readonly selectedVoice = computed(() => (this.missingVoice() ? '' : (this.prefs.value().voice ?? '')));
  protected readonly rate = computed(() => this.prefs.value().rate);
  protected readonly rateLabel = computed(() => rateText(this.rate()));

  protected onRate(event: Event): void {
    this.prefs.setRate(Number((event.target as HTMLInputElement).value));
  }

  protected testVoice(): void {
    this.speaker.preview(testVoiceSample(this.families()));
  }
```

`frontend/src/app/ui/primitives.spec.ts`, append to `RAW_CONTROL_ALLOWLIST`
after the command-palette entry:

```ts
  // v227: the voice rate slider. A range input has no primitive (this is the
  // app's only one), and a ui/ wrapper used exactly once is the worse trade;
  // its thumb takes the --hit-min square from voice-settings.ts.
  ['workspaces/system/voice-settings.ts', 'type="range"'],
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/workspaces/system/voice-settings.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/breakpoint-guard.spec.ts
```

Expected: PASS, `0 failed`. If the radius rule flags the track's corner, it
already reads `--chip-radius`; a flagged `4px` is the track height, not a
radius, so check the regex match before changing anything.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/system/voice-settings.ts frontend/src/app/workspaces/system/voice-settings.spec.ts frontend/src/app/ui/primitives.spec.ts
git commit -m "feat(ui): v227 voice block picker, rate slider and Test voice (V227-13)"
```

### Task V227-14: Layout audit at 390, 768 and 1440 px

**Model:** sonnet — a scripted audit run against a local replica and small CSS fixes in four named files; the procedure and the pass bar (exit 0) are fixed below.

One page per task (`docs/claude/ui-design.md` § UI tasks): the page is
`/system` (the Settings tab is its default tab) together with the shell top bar
the voice chip lives in, at phone, tablet and desktop widths. Runs after
V227-10 and V227-13.

**Files:**
- Modify (fixes only, when the audit reports one): `frontend/src/app/shell/voice-chip.ts`, `frontend/src/app/shell/shell.css`, `frontend/src/app/workspaces/system/voice-settings.ts`, `frontend/src/app/ui/switch.ts`, and the matching spec of each file touched (`voice-chip.spec.ts`, `shell.spec.ts`, `voice-settings.spec.ts`, `switch.spec.ts`)
- Create: `docs/superpowers/results/2026-11-12-v227-layout-audit.md`

**Interfaces:**
- Consumes: `sb-voice-chip` in `.status-cluster` (V227-10), `sb-voice-settings` with `<details class="voice" open>` (V227-12..13), `sb-switch` (V227-11). Tools: `frontend/scripts/layout-audit.mjs` (checks overflow, offscreen, clipped, tap, text, baseline, vcenter, hint, rail-label, dock; exit 0 clean, 1 findings, 2 cannot run), `frontend/scripts/browse.mjs` (`login`, `shots --clip`), `frontend/scripts/layout-audit-lib.mjs` `ROUTES` (already holds `/system`; no edit).
- Produces: the results doc; no code contract.

What the audit sees without clicking: every route's top bar with the chip in
its first state (headless Chromium ships `speechSynthesis`, so the chip reads
"Enable voice"; if the run shows "No voice on this browser" instead, that is
the 8 s unavailable state and it is audited just the same), and the whole
Voice block on `/system` (the `<details>` starts open, V227-12). The other chip
states change only the label; the longest label is checked with clipped
screenshots in Step 5.

- [ ] **Step 1: Prepare the local replica and the build**

```bash
# Top the shared replica up first (CLAUDE.md): run the /replicate-prod-db skill.
# The worktree's .env (gitignored) must point DATABASE_URL at the shared swing-db
# container on 127.0.0.1:56789; check the host and port without printing the value:
python - <<'EOF'
import re, pathlib
text = pathlib.Path(".env").read_text(encoding="utf-8")
m = re.search(r"^DATABASE_URL=.*@([^:/]+):(\d+)/", text, re.M)
print("DATABASE_URL host/port:", (m.group(1), m.group(2)) if m else "missing")
EOF
npm --prefix frontend run build
# admin_ui.py serves swingbot/admin/static/app, not dist: copy the fresh build over it.
cp -r frontend/dist/frontend/browser/. swingbot/admin/static/app/
ls frontend/dist/frontend/browser/main-*.js swingbot/admin/static/app/main-*.js
```

Expected: host/port `127.0.0.1`, `56789` (if not, edit that one line of the
worktree `.env` in place, never printing it); the build exits 0; the two
`main-*.js` names match (a stale bundle makes every later run measure old code).

- [ ] **Step 2: Start the admin and sign in once**

Start `python admin_ui.py` with `run_in_background` (it listens on
`http://localhost:1234` with the `.env` admin credentials), then:

```bash
node frontend/scripts/browse.mjs login --base http://localhost:1234
```

Expected: a stored session (browse.mjs signs in from `.env` itself; the values
are never typed, echoed or printed).

- [ ] **Step 3: Run the audit first**

```bash
node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440 --out "${TMPDIR:-/tmp}/v227-layout-audit"
echo "exit=$?"
```

Expected on a clean tree: `exit=0`. Any finding naming `sb-voice-chip`,
`.status-cluster`, `sb-voice-settings`, `sb-switch`, `.preview`, `.rate` or
`summary` is this task's to fix; a finding elsewhere that also appears on
`main` without this branch is recorded in the results doc and left alone (it is
not this page's regression). Never add an allow-list entry for these
components: they are neither canvas nor browser-native.

- [ ] **Step 4: Fix each finding, with a test that pins it**

Fix only in the files listed above, with tokens only (no colour literals, no
`@media (pointer: coarse)` block, breakpoints 640/1024/1440 only). Every fix
adds one source assertion to the matching spec, in the style the specs already
use. The two findings most likely here, and their pinned fixes:

The status cluster overflowing at 390 px with the chip's longest label
(`shell.css`, phone block; assertion in `shell.spec.ts`):

```css
  .status-cluster { flex-wrap: wrap; justify-content: flex-end; row-gap: var(--space-4); min-width: 0; }
```

```ts
it('lets the status cluster wrap on a phone rather than overflow (v227)', () => {
  const css = readFileSync(join(process.cwd(), 'src/app/shell/shell.css'), 'utf8');
  expect(css).toMatch(/\.status-cluster \{[^}]*flex-wrap: wrap;/);
});
```

A preview or summary under 44 px tall at 390/768 (`voice-settings.ts`;
assertion in `voice-settings.spec.ts`):

```css
    summary { display: flex; align-items: center; min-height: var(--hit-min); }
    .preview { flex: none; min-width: var(--hit-min); min-height: var(--hit-min); }
```

```ts
it('gives the summary and the previews a 44px touch target (v227 audit)', () => {
  const source = readFileSync(join(process.cwd(), 'src/app/workspaces/system/voice-settings.ts'), 'utf8');
  expect(source).toMatch(/summary \{[^}]*min-height: var\(--hit-min\);/);
  expect(source).toMatch(/\.preview \{[^}]*min-height: var\(--hit-min\);/);
});
```

Apply a fix only when the audit reports its finding. After each fix: rebuild,
copy the bundle (Step 1's last two commands), reload, and re-run Step 3 until
`exit=0` at all three widths.

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/shell/voice-chip.spec.ts --include src/app/shell/shell.spec.ts --include src/app/workspaces/system/voice-settings.spec.ts --include src/app/ui/switch.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/breakpoint-guard.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 5: Check the chip's other labels with clipped shots (at most 4 image reads)**

```bash
node frontend/scripts/browse.mjs shots --out "${TMPDIR:-/tmp}/v227-chip" --path /system --widths 390,768 --click "sb-voice-chip button" --clip ".status-cluster"
node frontend/scripts/browse.mjs shots --out "${TMPDIR:-/tmp}/v227-voice" --path /system --widths 390 --clip "sb-voice-settings"
```

The click moves the chip from "Enable voice" to "Voice on" or, in a headless
browser that refuses speech, "Voice blocked" (the longest button label). Read
the 390 and 768 cluster shots and the 390 block shot: the label sits beside its
icon on one line or wraps inside the chip, nothing is cut, the cluster stays in
the top bar (never in a menu), and the family groups stack in one column at
390. A problem found here is fixed the Step 4 way and the audit re-run.

- [ ] **Step 6: Record the results and stop the server**

Stop the background `admin_ui.py`. Create
`docs/superpowers/results/2026-11-12-v227-layout-audit.md` with the run's real
values in this shape:

```markdown
# v227 layout audit — voice chip and Settings → Voice notifications

**Plan:** [v227 part 3](../plans/2026-11-12-v227-voice-notifications_3-settings-release.md) (V227-14)
**Date:** 2026-11-12 · **Branch head:** <short sha the audit ran against>
**Command:** `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440`

| Width | First run exit | Findings on this page | Final run exit |
|---|---|---|---|
| 390 | … | … | 0 |
| 768 | … | … | 0 |
| 1440 | … | … | 0 |

## Fixes
- <file>: <finding> -> <change> (pinned by <spec test name>)

## Chip labels (clipped shots)
- 390 / 768: <label seen after the click>, <wraps or fits, nothing clipped>

## Findings left alone
- <route, check, element> — also on `main`, not this page's regression
```

Write "none" in a section with nothing to report; never leave a `<…>` marker
in the committed file.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/results/2026-11-12-v227-layout-audit.md
git commit -m "docs(v227): layout audit of the voice chip and Settings block at 390/768/1440 (V227-14)"
```

When Step 4 changed code, commit each fix with its spec first, scoped per file
(for example):

```bash
git add frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "fix(ui): v227 status cluster wraps on a phone with the voice chip (V227-14)"
```

Never commit `swingbot/admin/static/app/` (gitignored build output) or `.env`.

### Task V227-15: Release: merge, CI watch, panel, close-out, skill alignment

**Model:** sonnet — a scripted release ritual run by the controller (skills `worktree-lifecycle`, `panel`, `close-out`); one small skill-doc edit and its Codex mirror, no product code.

Runs last, after every other task is committed on the branch. The controller
runs this task itself (it needs `AskUserQuestion` and the skills); nothing in it
schedules the full suite: CI runs it after the push.

**Files:**
- Modify: `.claude/skills/alert-surface/SKILL.md` (one row in `## Known wrong turns`)
- Modify: `.agents/skills/alert-surface/SKILL.md` (regenerated by `python scripts/dev/sync_codex.py`, never hand-edited)
- Modify: `VERSION.json`, `version_history.json` (by `/close-out` only: ui minor, bot patch)

No `docs/claude/known-traps.md` or `AGENTS.md` change: the new trap is
specific to the alert surface and lives in its skill, and no `CLAUDE.md` /
`docs/claude/` text changes.

**Interfaces:**
- Consumes: every earlier task's commits on branch `2026-11-12-v227-voice-notifications`; `record_feed_post` (V227-4) at `swingbot/commands/scanning/alerts.py:_mirror` and `swingbot/core/scanning/lifecycle_embeds.py:_send_instruction` (V227-5); `config.FEED_POSTS_ENABLED` (V227-4).
- Produces: v227 merged on `main`, CI green, panel run, plan moved by `/close-out`.

- [ ] **Step 1: Narrow pre-merge checks in the worktree**

```bash
for t in tests/db/test_v227_feed_posts_schema.py tests/db/test_feed_posts_repository.py \
         tests/db/test_trigger_coverage.py tests/db/test_schema_contract.py \
         tests/presentation/test_feed_headline.py tests/infra/test_feed_posts_recorder.py \
         tests/infra/test_feed_posts_call_sites.py tests/infra/test_posted_log.py \
         tests/test_config_v227_keys.py tests/admin/test_api_v1_feed_posts.py \
         tests/admin/test_sse_contract.py tests/admin/test_access_contract.py \
         tests/scripts/test_rollback_migrations.py; do
  python scripts/dev/testrun.py file "$t" > "${TMPDIR:-/tmp}/v227-$(basename "$t" .py).log" 2>&1 \
    && echo "ok   $t" || echo "FAIL $t"
done
python scripts/dev/complexity_gate.py && echo "complexity ok"
python -m py_compile bot.py admin_ui.py swingbot/core/infra/feed_posts.py swingbot/core/presentation/feed_headline.py swingbot/core/db/repositories/feed_posts.py swingbot/admin/api_v1/feed_posts.py && echo "compile ok"
node frontend/scripts/ng-test.mjs frontend --include src/app/voice/voice-prefs.spec.ts --include src/app/voice/voice-speaker.spec.ts --include src/app/voice/voice-notifier.spec.ts --include src/app/shell/voice-chip.spec.ts --include src/app/shell/shell.spec.ts --include src/app/ui/switch.spec.ts --include src/app/workspaces/system/voice-settings.spec.ts --include src/app/workspaces/system/settings-tab.spec.ts --include src/app/api/event-stream.spec.ts --include src/app/api/api-client.spec.ts --include src/app/ui/primitives.spec.ts
```

Expected: every line `ok`, `complexity ok`, `compile ok`, the frontend run
`0 failed`. The DB files need `/replicate-prod-db` run once this session first
(shared `swing-db`, port 56789). A failure is fixed and that one file re-run
alone, never the suite.

- [ ] **Step 2: Align the alert-surface skill (close-out Step 5b, done before the merge so it ships in the branch)**

In `.claude/skills/alert-surface/SKILL.md`, append this row to the
`## Known wrong turns` table (after the "copy edit on the embed text" row):

```markdown
| "I'll post to the simple channel from a new sender" | Only `commands/scanning/alerts.py::_mirror` and the feed branch of `lifecycle_embeds._send_instruction` post there, and each calls `record_feed_post` right after `log_posted`, inside the `try` (v227). A new simple-channel sender without it never reaches bomeo-capital.com's voice notifications; a call outside the `try` speaks posts Discord refused. `FEED_POSTS_ENABLED=false` silences the site without touching Discord. |
```

Then regenerate the Codex mirror and check it:

```bash
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
git grep -n "record_feed_post" -- .claude/skills/alert-surface/SKILL.md .agents/skills/alert-surface/SKILL.md
git grep -n "def record_feed_post\|FEED_POSTS_ENABLED" -- swingbot/core/infra/feed_posts.py swingbot/config.py
```

Expected: `test_codex_mirror.py` `0 failed`; both skill copies name
`record_feed_post`; the symbols the row cites exist.

```bash
git add .claude/skills/alert-surface/SKILL.md .agents/skills/alert-surface/SKILL.md
git commit -m "docs(skills): alert-surface names the v227 simple-channel recorder and its kill switch (V227-15)"
```

- [ ] **Step 3: Ask the partner before merging**

`AskUserQuestion`, one question: "v227 voice notifications is complete on its
branch (narrow checks green, layout audit exit 0). Merge it into main and push?"
Options, recommended first: "Merge and push now (Recommended)", "Not yet —
leave it on the branch". On "Not yet", stop here and report the branch head.

- [ ] **Step 4: Merge through the worktree-lifecycle skill**

Run the `worktree-lifecycle` skill's merge path: `git fetch`, compare
`origin/main` with local `main` (another session may have committed), confirm
no concurrent session is mid-merge on `main`, then merge the branch into the
main tree with `--no-ff`:

```bash
git -C "E:/Documents/Private/Projects/Discord-Bot" fetch origin
git -C "E:/Documents/Private/Projects/Discord-Bot" status --short --branch
git -C "E:/Documents/Private/Projects/Discord-Bot" merge --no-ff 2026-11-12-v227-voice-notifications -m "Merge v227: voice notifications for simple-channel posts"
python -m alembic heads
```

Expected: a clean merge and exactly one Alembic head, `v227_001`. If `main`
gained a revision since V227-1 (two heads), stop: the revision's
`down_revision` must be rebased onto the new head in its own commit on the
branch, its tests re-run alone, and the merge retried.

- [ ] **Step 5: Push and watch CI until green**

```bash
git -C "E:/Documents/Private/Projects/Discord-Bot" push origin main
gh run list --branch main --limit 1 --json databaseId,status,headSha
```

Watch that run with `gh run watch <id> --exit-status` in the background
(`run_in_background`). On a failure: `gh run view <id> --log-failed > "${TMPDIR:-/tmp}/v227-ci.log"`,
read only the failing test's lines, fix it on `main` in a scoped commit, re-run
that one test alone (`python scripts/dev/testrun.py file <test>` or
`pytest <path>::<test>`), push, and watch the new run. Repeat until the run is
green (`0 failed`, `0 xfailed`).

- [ ] **Step 6: Panel on the merged diff**

Run `/panel ux-designer,staff-engineer` over the merged range
(`git diff <merge-base>..<merge commit>`, merge-base from
`git merge-base main^1 main^2` on the merge commit). A BLOCKING finding is
fixed on `main` with a test before close-out (scoped commit, the one test run
alone, push, CI watched as in Step 5); ADVISORY findings are recorded in the
close-out note.

- [ ] **Step 7: Close out**

Run `/close-out` (standing permission once every task is merged): it resolves
the bump from `VERSION.json` (ui minor, bot patch, as this plan's header
states), regenerates `version_history.json`, moves the spec's plan files
(`_0-index`, `_1-backend`, `_1b-recorder-admin`, `_2-voice-services`,
`_2b-chip-switch`, `_3-settings-release`) to `implemented/`, and removes the
worktree `.claude/worktrees/2026-11-12-v227-voice-notifications`. Deploying to
the Hetzner VM is not part of this plan: `/deploy` on the partner's call.

Expected: `git -C "E:/Documents/Private/Projects/Discord-Bot" log --oneline -3`
shows the close-out commit(s) on `main`, pushed; `git worktree list` no longer
lists the v227 worktree.

