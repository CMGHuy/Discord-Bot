# v239 — Bear-regime engine (shadow): Part 4 — frontend (banner, chip, layout audit)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-13" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md) — its `## Code reconciliation` section overrides the text above it.
**Index:** [2026-11-23-v239-bear-regime-engine-shadow_0-index.md](2026-11-23-v239-bear-regime-engine-shadow_0-index.md) — Global Constraints, Parallelisation, the task ledger and the eight "Decisions this index fixes" apply to every task here.

Tasks: V239-13 (wire types, `ApiClient.marketRegime`, `RegimeStore` and its pure `regimeBanner`), V239-14 (`sb-regime-chip` on trade and plan detail), V239-15 (`sb-regime-banner`, its shell mount, and the layout audit at 390 / 768 / 1440 on a seeded local replica). V239-13 needs V239-12's wire shape; V239-14 needs V239-9's wire keys; V239-13 ∥ V239-14; V239-15 needs both.

**Moved deliverable (index Handoff).** V239-13 as the ledger drew it passed 20 KB and the ledger has no `b` slot left, so the banner component, its spec and the shell mount (`shell/regime-banner.ts`, `shell/regime-banner.spec.ts`, `shell/shell.html`, `shell/shell.ts`, `shell/shell.spec.ts`) moved to V239-15, which already needed V239-13 and already owned the banner's styling. V239-13 keeps the wire types, the client method and the store.

**Restyle note.** Plans v240 (doctena night: tokens, type) and v241 (icons) are in flight on their own branches. These tasks build on current `main`'s components and use only tokens that exist today (`--warn`, `--warn-soft`, `--neg`, `--neg-soft`, `--text-muted`, `--text-chip`, `--space-*`, `--control-h`, `--border`). The banner and chip use no `sb-icon` and no glyph beyond the spec's chip prefixes (`×`, `!`, `↺`), so v241's glyph gate has nothing to swap. Whichever of v239 / v240 merges second re-runs V239-15's audit.

**Wire rule (V239-12, final).** `GET /api/v1/market/regime` returns `{mode, today, history, episode}`. `today` is the stored row for the current `D` (index decision 5) or `null`; under `mode = "off"` it is `{mode: "off", today: null, history: [], episode: null}`. `display` strings (`label`, `words`, `numbers`) come from `regime_text`; the SPA never builds regime vocabulary of its own beyond the chip's action words, which the spec fixes.

# Phase 4 — Frontend

### Task V239-13: SPA wire types, `ApiClient.marketRegime`, `RegimeStore`

**Model:** sonnet — a store on the `stores/tape-feed.ts` pattern and a pure view-model function; the state rules are fixed below and pinned by tests.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (after `TapeResponse`, ~L2581)
- Modify: `frontend/src/app/api/api-client.ts` (beside `tape()`, ~L650)
- Create: `frontend/src/app/stores/regime.store.ts`
- Create: `frontend/src/app/stores/regime.store.spec.ts`

**Interfaces:**
- Consumes: V239-12's JSON (index ledger row V239-12): `{mode: str, today: RegimeDayWire | null, history: RegimeDayWire[≤60], episode: {label: str, since_sessions: int} | null}`; `RegimeDayWire` = the 16 `bear_regime.ROW_COLUMNS` (`session_date`, `last_bar_date`, `state`, `stress`, `pullback_trigger`, `pullback_reason`, `spy_close`, `sma50`, `sma200`, `sma50_lag5`, `sma200_lag20`, `spy_high_prev`, `vix_close`, `vix_max5`, `spy_provider`, `vix_provider`) with ISO dates, plus `computed_at` (ISO) and `display: {label, words, numbers}`. Existing: `EventStream.changes(name, {minIntervalMs})`, `MARKET_DATA_MIN_INTERVAL_MS` (`api/event-stream.ts:46`).
- Produces (ledger contract, final; V239-15's banner reads `RegimeStore.banner` only):
  - `models.ts`: `RegimeState = 'BEAR' | 'CORRECTION' | 'NORMAL' | 'UNKNOWN'`; `RegimeAction = 'would_veto' | 'caution' | 'pullback_watch' | 'aligned' | 'none'`; `RegimeDisplay {label: string; words: string; numbers: string | null}`; `RegimeDay` (the wire row above); `RegimeEpisode {label: string; since_sessions: number}`; `RegimeResponse {mode: 'off' | 'shadow' | 'live'; today: RegimeDay | null; history: RegimeDay[]; episode: RegimeEpisode | null}`.
  - `ApiClient.marketRegime(): Observable<RegimeResponse>` (`GET ${base}/market/regime`).
  - `regime.store.ts`: `RegimeBanner {kind: 'reading' | 'none'; tone: 'bear' | 'correction' | 'muted'; label: string; since: number | null; numbers: string | null; words: string | null; pullback: boolean; accessibleName: string}` (the ledger shape plus `tone`, recorded in the index Handoff); pure `regimeBanner(res: RegimeResponse | null): RegimeBanner | null`; `@Injectable({providedIn: 'root'}) RegimeStore` with `banner: Signal<RegimeBanner | null>`, `status: Signal<'loading' | 'ready' | 'error'>`, `refresh(): void`.

**Banner rules this task fixes (spec § Dashboard banner; spec silent on the details). V239-15 renders exactly these fields:**
- Hidden (`regimeBanner` → `null`) when the response is `null`, `mode === 'off'`, `today === null`, or `today.state === 'NORMAL'`. The store also hides it while `status` is `'loading'` (before the first answer) and on `'error'`: an error clears the last response and calls `console.error`, so a stale label is never shown. A later refetch keeps the current banner until it answers (no flicker during a scan).
- `UNKNOWN` → `{kind: 'none', tone: 'muted', label: 'No reading', since: null, numbers: null, words: null, pullback: false, accessibleName: 'Regime: no reading'}`, rendered as the spec's literal single line `Regime: no reading`.
- A reading: `label = today.display.label`; `tone = 'bear'` for `BEAR`, else `'correction'`; `numbers = today.display.numbers`; `words` = `display.words` as a sentence (first letter upper-cased, a full stop added).
- **Pullback day** (`state === 'CORRECTION' && pullback_trigger === true`): `regime_text.display` labels that day `Pullback watch`, so the banner title takes the confirmed episode's label instead and adds the `Pullback watch` chip (`pullback: true`). With no episode, or an episode labelled `Normal` / `No reading` (a one-day correction), the title stays `Pullback watch` and no chip repeats it (`pullback: false`).
- `since = episode.since_sessions` only when `episode.label === label`; otherwise `null` (a day that is not yet a confirmed episode shows no count).
- `accessibleName = 'Regime ' + spoken(label) + (since !== null ? ', N sessions' : '') + (pullback ? ', pullback watch' : '') + (numbers ? '; ' + numbers : '')`, where `spoken('Correction · Stress') === 'Correction, stress'` (parts after the first lower-cased, joined by `, `). `N sessions` is singular for 1 (`1 session`). This is the spec's example form.

- [ ] **Step 1: Write the failing store spec**

Create `frontend/src/app/stores/regime.store.spec.ts`:

```ts
import { WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { RegimeDay, RegimeResponse } from '../api/models';
import { RegimeStore, regimeBanner } from './regime.store';

const NUMBERS = 'SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6';

function regimeDay(over: Partial<RegimeDay> = {}): RegimeDay {
  return {
    session_date: '2026-11-19', last_bar_date: '2026-11-18', state: 'CORRECTION', stress: true,
    pullback_trigger: false, pullback_reason: null, spy_close: 650, sma50: 716, sma200: 690,
    sma50_lag5: 720, sma200_lag20: 680, spy_high_prev: 655, vix_close: 37.6, vix_max5: 40.1,
    spy_provider: 'alpaca', vix_provider: 'yfinance', computed_at: '2026-11-18T21:05:00+00:00',
    display: { label: 'Correction · Stress', words: 'dip in an uptrend, high volatility', numbers: NUMBERS },
    ...over,
  };
}

function regimeResponse(over: Partial<RegimeResponse> = {}): RegimeResponse {
  return { mode: 'shadow', today: regimeDay(), history: [regimeDay()],
           episode: { label: 'Correction · Stress', since_sessions: 6 }, ...over };
}

const pullbackDay = regimeDay({
  stress: false, pullback_trigger: true,
  display: { label: 'Pullback watch', words: 'panic easing inside a correction', numbers: NUMBERS },
});

describe('regimeBanner', () => {
  it('reads a stress correction with its confirmed count and the number form', () => {
    expect(regimeBanner(regimeResponse())).toEqual({
      kind: 'reading', tone: 'correction', label: 'Correction · Stress', since: 6, numbers: NUMBERS,
      words: 'Dip in an uptrend, high volatility.', pullback: false,
      accessibleName: `Regime Correction, stress, 6 sessions; ${NUMBERS}`,
    });
  });

  it.each([
    ['no response', null],
    ['mode off', regimeResponse({ mode: 'off', today: null, history: [], episode: null })],
    ['no stored row for D', regimeResponse({ today: null })],
    ['NORMAL', regimeResponse({ today: regimeDay({ state: 'NORMAL', stress: false,
      display: { label: 'Normal', words: 'no correction or bear trend', numbers: NUMBERS } }) })],
  ])('is hidden on %s', (_name, res) => {
    expect(regimeBanner(res)).toBeNull();
  });

  it('shows a muted no-reading line on UNKNOWN and never the episode label', () => {
    const unknown = regimeDay({ state: 'UNKNOWN', stress: null, spy_close: null, sma50: null, sma200: null,
      vix_close: null, display: { label: 'No reading', words: '—', numbers: null } });
    expect(regimeBanner(regimeResponse({ today: unknown }))).toEqual({
      kind: 'none', tone: 'muted', label: 'No reading', since: null, numbers: null, words: null,
      pullback: false, accessibleName: 'Regime: no reading',
    });
  });

  it('keeps the correction title and adds the pullback chip on a pullback day', () => {
    const b = regimeBanner(regimeResponse({ today: pullbackDay, episode: { label: 'Correction', since_sessions: 3 } }))!;
    expect([b.label, b.pullback, b.since]).toEqual(['Correction', true, 3]);
    expect(b.words).toBe('Panic easing inside a correction.');
    expect(b.accessibleName).toBe(`Regime Correction, 3 sessions, pullback watch; ${NUMBERS}`);
  });

  it.each([null, { label: 'Normal', since_sessions: 9 }, { label: 'No reading', since_sessions: 2 }])(
    'titles a pullback day "Pullback watch" without a repeated chip when the episode is %o', (episode) => {
      const b = regimeBanner(regimeResponse({ today: pullbackDay, episode }))!;
      expect([b.label, b.pullback, b.since]).toEqual(['Pullback watch', false, null]);
    });

  it('drops the count when the confirmed episode carries another label (a one-day flicker)', () => {
    const b = regimeBanner(regimeResponse({ episode: { label: 'Correction', since_sessions: 4 } }))!;
    expect(b.since).toBeNull();
    expect(b.accessibleName).toBe(`Regime Correction, stress; ${NUMBERS}`);
  });

  it('gives BEAR the bear tone, a singular count and no numbers clause when numbers are null', () => {
    const bear = regimeDay({ state: 'BEAR', stress: null,
      display: { label: 'Bear', words: 'trend has turned down', numbers: null } });
    const b = regimeBanner(regimeResponse({ today: bear, episode: { label: 'Bear', since_sessions: 1 } }))!;
    expect([b.tone, b.label, b.numbers, b.accessibleName]).toEqual(['bear', 'Bear', null, 'Regime Bear, 1 session']);
  });
});

describe('RegimeStore', () => {
  let calls: Subject<RegimeResponse>[];
  let scan: WritableSignal<number>;

  beforeEach(() => {
    calls = [];
    scan = signal(0);
    const marketRegime = vi.fn(() => {
      const s = new Subject<RegimeResponse>();
      calls.push(s);
      return s;
    });
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: ApiClient, useValue: { marketRegime } },
        { provide: EventStream, useValue: { changes: () => scan } },
      ],
    });
  });
  afterEach(() => vi.restoreAllMocks());

  function start(): RegimeStore {
    const store = TestBed.inject(RegimeStore);
    TestBed.tick();
    return store;
  }

  it('is loading and hidden until the first answer, then shows it', () => {
    const store = start();
    expect([store.status(), store.banner()]).toEqual(['loading', null]);
    calls[0].next(regimeResponse());
    expect(store.status()).toBe('ready');
    expect(store.banner()?.label).toBe('Correction · Stress');
  });

  it('clears the banner and logs on a fetch error, never keeping a stale label', () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const store = start();
    calls[0].next(regimeResponse());
    store.refresh();
    calls[1].error(new Error('502'));
    expect([store.status(), store.banner()]).toEqual(['error', null]);
    expect(log).toHaveBeenCalledTimes(1);
  });

  it('keeps the shown banner while a refetch is in flight, and ignores a superseded answer', () => {
    const store = start();
    calls[0].next(regimeResponse());
    store.refresh();
    store.refresh();
    expect(store.banner()?.label).toBe('Correction · Stress');
    calls[1].next(regimeResponse({ today: null }));
    expect(store.banner()?.label).toBe('Correction · Stress');
    calls[2].next(regimeResponse({ mode: 'off', today: null, history: [], episode: null }));
    expect(store.banner()).toBeNull();
  });

  it('refetches when a scan event lands (the pass writes the row)', () => {
    start();
    scan.set(1);
    TestBed.tick();
    expect(calls.length).toBe(2);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --include src/app/stores/regime.store.spec.ts`
Expected: FAIL, the compiler cannot resolve `./regime.store` (and `RegimeDay` / `RegimeResponse` in `../api/models`).

- [ ] **Step 3: Add the wire types and the client method**

In `models.ts`, after `TapeResponse`, add a `/* -- bear regime (v239) -- */` block with the six types of the Interfaces block. `RegimeDay` fields: `session_date: string; last_bar_date: string | null; state: RegimeState; stress: boolean | null; pullback_trigger: boolean; pullback_reason: string | null;` the eight numbers (`spy_close`, `sma50`, `sma200`, `sma50_lag5`, `sma200_lag20`, `spy_high_prev`, `vix_close`, `vix_max5`) as `number | null`; `spy_provider: string | null; vix_provider: string | null; computed_at: string | null; display: RegimeDisplay`. Doc-comment the block: "v239: `GET /market/regime`; shadow only, labels come from the server's `regime_text`."

In `api-client.ts`, beside `tape()`, and add `RegimeResponse` to the `./models` import:

```ts
  /** v239: the daily bear-regime reading for the coming session (shadow). */
  marketRegime(): Observable<RegimeResponse> {
    return this.http.get<RegimeResponse>(`${this.base}/market/regime`);
  }
```

- [ ] **Step 4: Implement `regime.store.ts`**

`regimeBanner(res)` follows the rules block above; keep every function under complexity 15 by splitting into module-private `isHidden(res)`, `unknownBanner()`, `readingBanner(today, episode)`, `titleFor(today, episode)`, `sentence(words)` and `spoken(label)`. The pullback title rule:

```ts
const NOT_A_CORRECTION_EPISODE = new Set(['Normal', 'No reading']);

function titleFor(today: RegimeDay, episode: RegimeEpisode | null): { label: string; pullback: boolean } {
  const pullbackDay = today.state === 'CORRECTION' && today.pullback_trigger === true;
  if (pullbackDay && episode && !NOT_A_CORRECTION_EPISODE.has(episode.label)) {
    return { label: episode.label, pullback: true };
  }
  return { label: today.display.label, pullback: false };
}
```

`RegimeStore`, modelled on `stores/tape-feed.ts` but clearing on error:

```ts
@Injectable({ providedIn: 'root' })
export class RegimeStore {
  private readonly api = inject(ApiClient);
  private readonly response = signal<RegimeResponse | null>(null);
  private readonly _status = signal<'loading' | 'ready' | 'error'>('loading');
  private latest = 0;

  readonly status = this._status.asReadonly();
  readonly banner = computed(() => (this._status() === 'ready' ? regimeBanner(this.response()) : null));

  constructor() {
    // The scan pass writes the day's row; `scan` fires ~1/s while a scan runs.
    const scan = inject(EventStream).changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
    effect(() => {
      scan();
      untracked(() => this.refresh());
    });
  }

  refresh(): void {
    const request = ++this.latest;
    this.api.marketRegime().subscribe({
      next: (res) => {
        if (request !== this.latest) return;
        this.response.set(res ?? null);
        this._status.set('ready');
      },
      error: (err: unknown) => {
        if (request !== this.latest) return;
        console.error('regime: /market/regime failed; the banner stays hidden', err);
        this.response.set(null);
        this._status.set('error');
      },
    });
  }
}
```

- [ ] **Step 5: Run the store spec to verify it passes**

Run: `cd frontend && npx ng test --include src/app/stores/regime.store.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/regime.store.ts frontend/src/app/stores/regime.store.spec.ts
git commit -m "feat(v239): regime wire types, client method and RegimeStore"
```

### Task V239-14: Regime chip on trade detail and plan detail

**Model:** sonnet — one presentational component and a lookup table, mounted on two existing tag rows with spec-pinned words, colours and prefixes.

**Files:**
- Create: `frontend/src/app/workspaces/trades/why/regime-chip.ts`
- Create: `frontend/src/app/workspaces/trades/why/regime-chip.spec.ts`
- Modify: `frontend/src/app/workspaces/trades/trade-detail.ts` (the `.tags` row in the identity block, ~L207; `imports: [...]`, ~L132)
- Modify: `frontend/src/app/workspaces/plans/plan-detail.ts` (the `.tags` row, ~L146; `imports: [...]`, ~L113)
- Modify: `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (a new describe)
- Modify: `frontend/src/app/workspaces/plans/plan-detail.spec.ts` (two tests in `describe('PlanDetail')`)

**Interfaces:**
- Consumes: V239-9's wire keys — `trade_why.WIRE_CONTEXT_KEYS` gains `bear_regime` and `regime_action`, so `TradeDetailStore.detail()?.entry_context` (`Record<string, unknown>`, `api/models.ts:381`) carries them on plans stamped after v239 ships; legacy plans lack them. `regime_action` values: `would_veto`, `caution`, `pullback_watch`, `aligned`, `none` (`bear_regime.WOULD_VETO` … `NONE`). Existing: `Chip` and `ChipTone` (`ui/chip.ts`).
- Produces (ledger contract, final): `regimeChip(ctx: Record<string, unknown> | null | undefined) -> {label: string; tone: ChipTone; prefix: string} | null`; standalone `RegimeChip`, selector `sb-regime-chip`, `context = input<Record<string, unknown> | null | undefined>(null)`. Nothing in this task imports from V239-13 (no `RegimeAction` import: the chip reads an untyped `entry_context`).

**Chip rules (spec § Plan-card chip, reconciliation 8):**
- It reads the plan's own stamped `regime_action`, never today's state, so an old card keeps the regime it was issued under.
- `would_veto` → `would skip`, tone `bad` (red), prefix `×`; `caution` → `caution`, `warn` (amber), `!`; `pullback_watch` → `pullback watch`, `info` (blue), `↺`; `aligned` → `aligned`, `neutral`, no prefix. The rendered text is `prefix + ' ' + label` (or the label alone), lower case (`[caps]="false"`), so colour is never the only cue.
- No chip when `entry_context` is missing, has no `regime_action`, has `none`, or has any other value (an unknown or non-string action is treated as legacy, never guessed).
- Placement: the first item of the `.tags` row, which sits directly under the title line that carries the direction (`side()` on trade detail, the direction `.tag` on plan detail). Below 640 px the chip takes its own line (`flex-basis: 100%` on the host) and is never truncated (no `text-overflow`, no `max-width`).
- The host carries `title="Regime when issued: <label> (shadow, no effect on this plan)"` and the same words as visually hidden text before the chip, so a screen reader hears what the chip is.

- [ ] **Step 1: Write the failing chip spec**

Create `frontend/src/app/workspaces/trades/why/regime-chip.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { RegimeChip, regimeChip } from './regime-chip';

describe('regimeChip', () => {
  it.each([
    ['would_veto', { label: 'would skip', tone: 'bad', prefix: '×' }],
    ['caution', { label: 'caution', tone: 'warn', prefix: '!' }],
    ['pullback_watch', { label: 'pullback watch', tone: 'info', prefix: '↺' }],
    ['aligned', { label: 'aligned', tone: 'neutral', prefix: '' }],
  ])('maps %s to its words, colour and text prefix', (action, chip) => {
    expect(regimeChip({ bear_regime: 'CORRECTION', regime_action: action })).toEqual(chip);
  });

  it.each([
    ['no context', null],
    ['undefined context', undefined],
    ['a legacy plan without the keys', { rs_pctile: 62 }],
    ['a state without an action', { bear_regime: 'BEAR' }],
    ['action none', { bear_regime: 'NORMAL', regime_action: 'none' }],
    ['an unknown action', { regime_action: 'would_short' }],
    ['a non-string action', { regime_action: 42 }],
  ])('shows no chip for %s', (_name, ctx) => {
    expect(regimeChip(ctx as Record<string, unknown> | null | undefined)).toBeNull();
  });

  it("reads the stamped action, never the plan's state or today's", () => {
    expect(regimeChip({ bear_regime: 'NORMAL', regime_action: 'would_veto' })?.label).toBe('would skip');
  });
});

describe('sb-regime-chip', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(context: Record<string, unknown> | null): HTMLElement {
    const fixture = TestBed.createComponent(RegimeChip);
    fixture.componentRef.setInput('context', context);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders the prefix, the words and the tone, lower case', () => {
    const el = render({ bear_regime: 'BEAR', regime_action: 'would_veto' });
    const chip = el.querySelector('sb-chip .chip') as HTMLElement;
    expect(chip.textContent?.trim()).toBe('× would skip');
    expect(chip.classList).toContain('bad');
    expect(chip.classList).not.toContain('caps');
  });

  it('renders an aligned chip without a prefix', () => {
    expect(render({ regime_action: 'aligned' }).querySelector('sb-chip')?.textContent?.trim()).toBe('aligned');
  });

  it('names itself for hover and for assistive tech', () => {
    const el = render({ regime_action: 'caution' });
    expect(el.querySelector('.regime-chip')?.getAttribute('title'))
      .toBe('Regime when issued: caution (shadow, no effect on this plan)');
    expect(el.querySelector('.sr')?.textContent?.trim()).toBe('Regime when issued:');
  });

  it('renders nothing for a legacy plan', () => {
    expect(render({ rs_pctile: 62 }).querySelector('.regime-chip')).toBeNull();
  });

  it('takes its own line on a phone and is never truncated', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/trades/why/regime-chip.ts'), 'utf8');
    expect(src).toMatch(/@media \(max-width: 639px\) \{\s*:host \{ flex-basis: 100%; \}/);
    expect(src).not.toMatch(/text-overflow|max-width: \d/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --include src/app/workspaces/trades/why/regime-chip.spec.ts`
Expected: FAIL, `./regime-chip` cannot be resolved.

- [ ] **Step 3: Implement `regime-chip.ts`**

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { Chip, ChipTone } from '../../../ui/chip';

export interface RegimeChipView { label: string; tone: ChipTone; prefix: string }

/** v239: the engine's shadow action stamped on the plan at issue (spec § Plan-card chip). */
const CHIPS: Readonly<Record<string, RegimeChipView>> = {
  would_veto: { label: 'would skip', tone: 'bad', prefix: '×' },
  caution: { label: 'caution', tone: 'warn', prefix: '!' },
  pullback_watch: { label: 'pullback watch', tone: 'info', prefix: '↺' },
  aligned: { label: 'aligned', tone: 'neutral', prefix: '' },
};

export function regimeChip(ctx: Record<string, unknown> | null | undefined): RegimeChipView | null {
  const action = ctx?.['regime_action'];
  return typeof action === 'string' && Object.hasOwn(CHIPS, action) ? { ...CHIPS[action] } : null;
}
```

Component: selector `sb-regime-chip`, `OnPush`, `imports: [Chip]`, `readonly context = input<Record<string, unknown> | null | undefined>(null)`, `protected readonly chip = computed(() => regimeChip(this.context()))`, `protected readonly title = computed(...)` giving the title string above. Template:

```html
@if (chip(); as c) {
  <span class="regime-chip" [attr.title]="title()">
    <span class="sr">Regime when issued: </span>
    <sb-chip [label]="c.prefix ? c.prefix + ' ' + c.label : c.label" [tone]="c.tone" [caps]="false" />
  </span>
}
```

Styles:

```css
:host { display: inline-flex; flex: none; }
.regime-chip { display: inline-flex; align-items: baseline; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (max-width: 639px) {
  :host { flex-basis: 100%; }
}
```

- [ ] **Step 4: Run the chip spec to verify it passes**

Run: `cd frontend && npx ng test --include src/app/workspaces/trades/why/regime-chip.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Write the failing page tests**

Append to `frontend/src/app/workspaces/trades/trade-detail.spec.ts` (it reuses the file's `ID`, `DETAIL`, `tradeResponse`, `signInAs`, `FakeEventStream` and the identity describe's providers):

```ts
describe('TradeDetail — regime chip (v239)', () => {
  let backend: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: LiveValuesStore, useClass: FakeLiveValues },
        TradeDetailStore,
        ChartStore,
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    signInAs('admin');
    backend = TestBed.inject(HttpTestingController);
  });

  function tagRow(entryContext?: Record<string, unknown>): HTMLElement {
    const fixture = TestBed.createComponent(TradeDetail);
    fixture.componentRef.setInput('id', ID);
    fixture.componentRef.setInput('tab', 'overview');
    fixture.detectChanges();
    const detail = entryContext === undefined ? DETAIL : { ...DETAIL, entry_context: entryContext };
    backend.expectOne(`/api/v1/trades/${ID}`).flush(tradeResponse(detail));
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).querySelector('header.head > .identity > .tags') as HTMLElement;
  }

  it('leads the tag row, under the side label, with the stamped action', () => {
    const row = tagRow({ bear_regime: 'CORRECTION', regime_action: 'would_veto' });
    expect(row.firstElementChild?.tagName.toLowerCase()).toBe('sb-regime-chip');
    expect(row.querySelector('sb-regime-chip')?.textContent).toContain('× would skip');
  });

  it.each([
    ['without entry_context', undefined],
    ['legacy keys only', { rs_pctile: 62 }],
    ['action none', { bear_regime: 'NORMAL', regime_action: 'none' }],
  ])('shows no regime chip %s', (_name, ctx) => {
    expect(tagRow(ctx).querySelector('sb-regime-chip')).toBeNull();
  });
});
```

Add the names this describe needs to the file's imports only where they are missing (`HttpTestingController`, `provideHttpClientTesting`, `provideZonelessChangeDetection`, the three interceptors are already imported for the identity describe).

In `frontend/src/app/workspaces/plans/plan-detail.spec.ts`, inside `describe('PlanDetail')`:

```ts
  it('leads the tag row with the regime chip the plan was issued under (v239)', () => {
    const el = render('PENDING', {}, { entry_context: { bear_regime: 'CORRECTION', regime_action: 'pullback_watch' } });
    const row = el.querySelector('header.plan-head > .tags') as HTMLElement;
    expect(row.firstElementChild?.tagName.toLowerCase()).toBe('sb-regime-chip');
    expect(row.querySelector('sb-regime-chip')?.textContent).toContain('↺ pullback watch');
  });

  it('shows no regime chip on a legacy plan (v239)', () => {
    expect(render('ACTIVE').querySelector('sb-regime-chip')).toBeNull();
  });
```

(`DETAIL.entry_context` there is `{ rs_pctile: 62, gap_p90_pct: 1.85, gap_fragile: false }`, a legacy context.)

- [ ] **Step 6: Run them to verify they fail**

Run: `cd frontend && npx ng test --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/plans/plan-detail.spec.ts`
Expected: FAIL in the two positive tests (`firstElementChild` is the horizon / strategy tag, not `sb-regime-chip`); the no-chip tests pass already.

- [ ] **Step 7: Mount the chip on both pages**

Both pages mount the host only when there is a chip, so a legacy plan's tag row keeps no empty flex item (an empty item would still take a `gap`). Each page gets the same `computed` (it imports `regimeChip` and `RegimeChip`):

```ts
  /** v239: the stamped entry_context when it carries a regime chip, else null. */
  protected readonly regimeContext = computed(() => {
    const ctx = this.store.detail()?.entry_context ?? null;
    return regimeChip(ctx) ? ctx : null;
  });
```

`trade-detail.ts`: import `RegimeChip, regimeChip` from `'./why/regime-chip'`, add `RegimeChip` to `imports: [...]`, and make the chip the first child of `<div class="tags">` in the identity block:

```html
                <div class="tags">
                  <!-- v239: the regime the plan was issued under (shadow). -->
                  @if (regimeContext(); as ctx) {
                    <sb-regime-chip [context]="ctx" />
                  }
                  @if (trade.horizon) {
```

`plan-detail.ts`: the same, importing from `'../trades/why/regime-chip'`, as the first child of its `<div class="tags">` (before `@if (strategyLine(); as line)`).

- [ ] **Step 8: Run the four specs to verify they pass**

Run: `cd frontend && npx ng test --include src/app/workspaces/trades/why/regime-chip.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/workspaces/plans/plan-detail.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/regime-chip.ts frontend/src/app/workspaces/trades/why/regime-chip.spec.ts frontend/src/app/workspaces/trades/trade-detail.ts frontend/src/app/workspaces/plans/plan-detail.ts frontend/src/app/workspaces/trades/trade-detail.spec.ts frontend/src/app/workspaces/plans/plan-detail.spec.ts
git commit -m "feat(v239): regime chip on trade and plan detail"
```

### Task V239-15: `sb-regime-banner` in the shell, and the layout audit at 390 / 768 / 1440

**Model:** sonnet — a presentational component with tests written out, then a run-and-fix audit loop on a seeded local replica; the seed is a fixed scratch script.

**Files:**
- Create: `frontend/src/app/shell/regime-banner.ts` (moved here from V239-13, see the part header)
- Create: `frontend/src/app/shell/regime-banner.spec.ts`
- Modify: `frontend/src/app/shell/shell.html` (after the `.tape-strip` div, L137-139)
- Modify: `frontend/src/app/shell/shell.ts` (import, and `imports: [...]` at L87-91)
- Modify: `frontend/src/app/shell/shell.spec.ts` (the `.main` children test at L151; a new describe at the end)
- Modify: `frontend/src/app/workspaces/trades/why/regime-chip.ts` (only if the audit finds a chip defect)
- Modify: `frontend/scripts/layout-audit.allow.json` (only for a documented false positive: canvas, third-party chart internals or a browser-native part, per `docs/claude/ui-design.md`; an app control is fixed, never allowed)
- Scratch, never committed: `<scratchpad>/v239_audit_seed.py`

**Interfaces:**
- Consumes: V239-13 — `RegimeStore.banner: Signal<RegimeBanner | null>` and the `RegimeBanner` shape with its rules (V239-13 § Banner rules); V239-14 — `sb-regime-chip` on the two `.tags` rows; V239-6b — `market_regime_repo().insert_once(row, *, notice_event=None) -> bool`; V239-2 — `bear_regime.RegimeDay(...).to_row()`, `bear_regime.CORRECTION`; V239-4 — `regime_calendar.session_pair(now) -> (s, D)`; V239-12's wire (part header). Existing: `Chip` (`ui/chip.ts`), `ViewportService`, `shellProviders()` / `createShell()` in `shell.spec.ts`, `frontend/scripts/layout-audit.mjs`, `frontend/scripts/browse.mjs` (`login`, `api`, `shots --clip --click`).
- Produces: standalone `RegimeBannerComponent`, selector `sb-regime-banner`, no inputs (it injects `RegimeStore`), mounted once in the shell. Nothing later consumes it.

**Component rules (spec § Dashboard banner):** collapsed it shows `Trend: <label>`, `since N sessions` (singular for 1), the `Pullback watch` chip, and the number line (the inline number line is hidden below 640 px; it stays in the expanded panel and in the accessible name). Expanded, it shows the number line and the plain-words sentence. The collapsed banner is a native `<button type="button">` (so Enter and Space toggle it) with `min-height: 44px` at every width. `UNKNOWN` is the muted, non-interactive line `Regime: no reading`. On a phone the banner sits directly under the top bar (the tape strip is hidden below 640 px); wider, it is the full-width strip under the tape.

- [ ] **Step 1: Write the failing banner spec**

Create `frontend/src/app/shell/regime-banner.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { RegimeBanner, RegimeStore } from '../stores/regime.store';
import { RegimeBannerComponent } from './regime-banner';

const NUMBERS = 'SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6';
const READING: RegimeBanner = {
  kind: 'reading', tone: 'correction', label: 'Correction · Stress', since: 6, numbers: NUMBERS,
  words: 'Dip in an uptrend, high volatility.', pullback: false,
  accessibleName: `Regime Correction, stress, 6 sessions; ${NUMBERS}`,
};
const empty = (el: HTMLElement) => el.innerHTML.replace(/<!--[\s\S]*?-->/g, '').trim();

describe('sb-regime-banner', () => {
  let banner: WritableSignal<RegimeBanner | null>;

  beforeEach(() => {
    banner = signal<RegimeBanner | null>(null);
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(),
                  { provide: RegimeStore, useValue: { banner, status: signal('ready'), refresh: () => undefined } }],
    });
  });

  function render(value: RegimeBanner | null): HTMLElement {
    banner.set(value);
    const fixture = TestBed.createComponent(RegimeBannerComponent);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders nothing without a banner (NORMAL, off, loading, error)', () => {
    expect(empty(render(null))).toBe('');
  });

  it('shows the muted no-reading line on UNKNOWN, with no control', () => {
    const el = render({ ...READING, kind: 'none', tone: 'muted', label: 'No reading', since: null,
                        numbers: null, words: null, accessibleName: 'Regime: no reading' });
    expect(el.querySelector('[role="status"]')?.textContent?.trim()).toBe('Regime: no reading');
    expect(el.querySelector('button')).toBeNull();
  });

  it('shows the Trend: prefix, the label, the count and the numbers on a collapsed native button', () => {
    const button = render(READING).querySelector('button')!;
    expect(button.getAttribute('type')).toBe('button');
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(button.getAttribute('aria-label')).toBe(READING.accessibleName);
    expect(button.querySelector('.lead')?.textContent?.trim()).toBe('Trend: Correction · Stress');
    expect(button.querySelector('.since')?.textContent?.trim()).toBe('since 6 sessions');
    expect(button.querySelector('.numbers')?.textContent?.trim()).toBe(NUMBERS);
    expect(button.querySelector('sb-chip')).toBeNull();
  });

  it('toggles aria-expanded and the plain-words panel (a native button: Enter and Space click it)', () => {
    const el = render(READING);
    const button = el.querySelector('button')!;
    const panel = el.querySelector(`#${button.getAttribute('aria-controls')}`) as HTMLElement;
    expect(panel.hidden).toBe(true);
    button.click();
    TestBed.tick();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(panel.hidden).toBe(false);
    expect(panel.textContent).toContain('Dip in an uptrend, high volatility.');
    expect(panel.textContent).toContain(NUMBERS);
    button.click();
    TestBed.tick();
    expect(button.getAttribute('aria-expanded')).toBe('false');
  });

  it('adds the Pullback watch chip on a pullback day and singularises one session', () => {
    const button = render({ ...READING, label: 'Correction', since: 1, pullback: true }).querySelector('button')!;
    expect(button.querySelector('sb-chip')?.textContent?.trim()).toBe('Pullback watch');
    expect(button.querySelector('.since')?.textContent?.trim()).toBe('since 1 session');
  });

  it('omits the count and the numbers when they are null', () => {
    const button = render({ ...READING, since: null, numbers: null }).querySelector('button')!;
    expect(button.querySelector('.since')).toBeNull();
    expect(button.querySelector('.numbers')).toBeNull();
  });

  it('keeps a 44px target at every width, hides the inline numbers on a phone, and uses no glyph', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/shell/regime-banner.ts'), 'utf8');
    expect(src).toMatch(/\.regime-toggle \{[^}]*min-height: 44px;/);
    expect(src).toMatch(/@media \(max-width: 639px\) \{[^}]*\.numbers \{ display: none; \}/);
    expect(src).not.toMatch(/[⚠✕✖↓↑]/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx ng test --include src/app/shell/regime-banner.spec.ts`
Expected: FAIL, `./regime-banner` cannot be resolved.

- [ ] **Step 3: Implement `shell/regime-banner.ts`**

Standalone, `OnPush`, `imports: [Chip]`, `protected readonly banner = inject(RegimeStore).banner`, `protected readonly open = signal(false)`. Template:

```html
@if (banner(); as b) {
  @if (b.kind === 'none') {
    <div class="regime-strip" data-tone="muted" role="status">Regime: no reading</div>
  } @else {
    <div class="regime-strip" [attr.data-tone]="b.tone">
      <button type="button" class="regime-toggle" aria-controls="regime-detail"
              [attr.aria-expanded]="open()" [attr.aria-label]="b.accessibleName" (click)="open.set(!open())">
        <span class="lead">Trend: {{ b.label }}</span>
        @if (b.since !== null) {
          <span class="since">since {{ b.since }} {{ b.since === 1 ? 'session' : 'sessions' }}</span>
        }
        @if (b.pullback) { <sb-chip label="Pullback watch" tone="info" [caps]="false" /> }
        @if (b.numbers) { <span class="numbers num">{{ b.numbers }}</span> }
      </button>
      <div id="regime-detail" class="regime-detail" [hidden]="!open()">
        @if (b.numbers) { <p class="num">{{ b.numbers }}</p> }
        @if (b.words) { <p>{{ b.words }}</p> }
      </div>
    </div>
  }
}
```

Styles (tokens only; the spec test pins the two rules it names):

```css
:host { display: block; }
.regime-strip { border-bottom: 1px solid var(--warn); background: var(--warn-soft); color: var(--warn); }
.regime-strip[data-tone='bear'] { border-color: var(--neg); background: var(--neg-soft); color: var(--neg); }
.regime-strip[data-tone='muted'] { display: flex; align-items: center; min-height: 44px;
  padding: 0 var(--space-14); border-color: var(--border); background: transparent;
  color: var(--text-muted); font-size: var(--text-chip); }
.regime-toggle { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-6) var(--space-10);
  width: 100%; min-height: 44px; padding: var(--space-6) var(--space-14); border: 0; background: none;
  color: inherit; font: inherit; font-size: var(--text-chip); text-align: left; cursor: pointer; }
.lead { font-weight: 650; }
.since, .numbers { color: var(--text-secondary); }
.regime-detail { padding: 0 var(--space-14) var(--space-8); font-size: var(--text-chip); color: var(--text-secondary); }
.regime-detail p { margin: 0; }
@media (max-width: 639px) { .numbers { display: none; } }
```

- [ ] **Step 4: Mount it in the shell**

`shell.html`, directly after the `.tape-strip` div (L137-139):

```html
    <!-- v239: the daily trend (bear regime, shadow). Below 640px the tape
         strip is hidden, so this sits directly under the top bar and its
         shock pill ("intraday: Shock" / "Trend: Correction"); wider, it is a
         full-width strip under the tape. Renders nothing on NORMAL / off. -->
    <sb-regime-banner />
```

`shell.ts`: `import { RegimeBannerComponent } from './regime-banner';` and add `RegimeBannerComponent` to `imports: [...]`.

`shell.spec.ts`: the test at L151 (`runs the tape as a strip under the top bar`) now expects `['header', 'div', 'sb-regime-banner', 'sb-refresher-banner', 'div']` and reads the workspace row at `main.children[4]`. Add the imports `RegimeBanner, RegimeStore` from `'../stores/regime.store'` and append:

```ts
const REGIME_READING: RegimeBanner = {
  kind: 'reading', tone: 'correction', label: 'Correction', since: 3, numbers: null,
  words: 'Dip in an uptrend.', pullback: false, accessibleName: 'Regime Correction, 3 sessions',
};

describe('shell regime banner (v239)', () => {
  function mount(phone: boolean): HTMLElement {
    TestBed.configureTestingModule({ providers: shellProviders() });
    TestBed.overrideProvider(RegimeStore, {
      useValue: { banner: signal(REGIME_READING), status: signal('ready'), refresh: vi.fn() },
    });
    TestBed.overrideProvider(ViewportService, {
      useValue: { isPhone: signal(phone), isNarrow: signal(phone), viewport: signal(phone ? 'xs' : 'md') },
    });
    const fixture = createShell();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it.each([true, false])('sits directly after the tape strip, outside the top bar (phone=%s)', (phone) => {
    const main = mount(phone).querySelector('.main')!;
    const tags = [...main.children].map((c) => c.tagName.toLowerCase());
    expect(tags.indexOf('sb-regime-banner')).toBe(tags.indexOf('header') + 2);
    expect(main.children[1].classList).toContain('tape-strip');
    expect(main.querySelector('header.topbar sb-regime-banner')).toBeNull();
    expect(main.querySelector('sb-regime-banner .lead')?.textContent?.trim()).toBe('Trend: Correction');
  });
});
```

If another shell describe now fails on an unexpected `/api/v1/market/regime` request (an `expectNone` / `match` on the testing backend), give that describe the same `RegimeStore` fake; never flush the request from unrelated tests.

- [ ] **Step 5: Run the specs to verify they pass**

Run: `cd frontend && npx ng test --include src/app/shell/regime-banner.spec.ts --include src/app/shell/shell.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Commit the banner**

```bash
git add frontend/src/app/shell/regime-banner.ts frontend/src/app/shell/regime-banner.spec.ts frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.spec.ts
git commit -m "feat(v239): Trend banner in the app shell, under the tape strip"
```

- [ ] **Step 7: Prepare the local replica and seed the worst case**

Run `/replicate-prod-db` (the shared `swing-db` container, `.env` credentials, never printed). Then, from the worktree root: `python -m alembic upgrade head` (adds V239-6's `market_regime_days` to the replica; prod gains the same revision on deploy), `cd frontend && npm run build`, start `python admin_ui.py` in the background, and sign in once with `node frontend/scripts/browse.mjs login --base http://localhost:1234` (it reads `.env`'s `ADMIN_USERNAME` / `ADMIN_PASSWORD` itself; never echo them).

Read the two trade ids the audit will visit, exactly as `pickIds` does (`items[0].id`): `node frontend/scripts/browse.mjs api --path "/api/v1/trades?status=CLOSED&per_page=1"` (for `/trades/:id`) and `... "/api/v1/trades?status=OPEN&per_page=1"`, else `status=PENDING` (for `/plans/:plan`).

Write `<scratchpad>/v239_audit_seed.py` (scratch, never committed). `--apply` writes the widest banner (a stress correction confirmed over two sessions, `D` a pullback day: "Trend: Correction · Stress", "since 2 sessions", the chip and the numbers) and stamps the two audited trades; `--undo` removes exactly what `--apply` added, using the state file:

```python
"""V239-15 layout-audit seed for the local replica only. Never run against production."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

from swingbot.core.db.engine import get_engine
from swingbot.core.db.repositories.market_regime import market_regime_repo
from swingbot.core.market import bear_regime as br
from swingbot.core.scanning.regime_calendar import session_pair

SEED = "v239-15-audit"
NUMBERS = dict(spy_close=650.0, sma50=716.0, sma200=690.0, vix_close=37.6)
STAMP = sa.text(
    "UPDATE trades SET doc = jsonb_set(jsonb_set(doc, '{entry_context,bear_regime}', '\"CORRECTION\"'),"
    " '{entry_context,regime_action}', to_jsonb(CAST(:action AS text)))"
    " WHERE trade_id = :tid AND doc ? 'entry_context' AND NOT doc->'entry_context' ? 'regime_action'")
UNSTAMP = sa.text("UPDATE trades SET doc = doc #- '{entry_context,bear_regime}' #- '{entry_context,regime_action}'"
                  " WHERE trade_id = :tid")
DROP = sa.text("DELETE FROM market_regime_days WHERE session_date = :day AND doc->>'seed' = :seed")


def apply(trade_ids: list[str], state: Path) -> None:
    s, d = session_pair(datetime.now(timezone.utc))
    days = []
    for day in (s, d):
        row = br.RegimeDay(session_date=day, last_bar_date=s, state=br.CORRECTION, stress=True,
                           pullback_trigger=day == d, **NUMBERS).to_row()
        row["doc"] = {**row["doc"], "seed": SEED}
        if market_regime_repo().insert_once(row):
            days.append(day.isoformat())
    stamped = []
    with get_engine().begin() as conn:
        for tid, action in zip(trade_ids, ("would_veto", "pullback_watch")):
            if conn.execute(STAMP, {"tid": tid, "action": action}).rowcount:
                stamped.append(tid)
    state.write_text(json.dumps({"days": days, "trades": stamped}), encoding="utf-8")
    print(f"seeded days={days} trades={stamped}")


def undo(state: Path) -> None:
    seeded = json.loads(state.read_text(encoding="utf-8"))
    with get_engine().begin() as conn:
        for day in seeded["days"]:
            conn.execute(DROP, {"day": day, "seed": SEED})
        for tid in seeded["trades"]:
            conn.execute(UNSTAMP, {"tid": tid})
    state.unlink()
    print("seed removed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", nargs="*", metavar="TRADE_ID")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--state", type=Path, required=True)
    args = ap.parse_args()
    undo(args.state) if args.undo else apply(args.apply or [], args.state)
```

Run: `python <scratchpad>/v239_audit_seed.py --state <scratchpad>/v239_seed.json --apply <closed id> <open-or-pending id>`
Expected: `seeded days=['<s>', '<D>'] trades=[...both ids...]`. Confirm through the API: `node frontend/scripts/browse.mjs api --path /api/v1/market/regime` shows `today.session_date == D` and `episode.since_sessions == 2`; `... --path /api/v1/trades/<closed id>` shows `entry_context.regime_action == "would_veto"`. If either is missing, stop and report `BLOCKED:` with the API output (the replica or the wire differs from V239-6b / V239-9 / V239-12); never patch the app to fit the seed.

- [ ] **Step 8: Run the layout audit at all three widths**

Run: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234`
Expected: exit 0 at 390, 768 and 1440 on every route (the banner is in the shell, so every route carries it; `/trades/:id` and `/plans/:plan` carry the chip). Exit 1 lists findings: fix each one in `regime-banner.ts` or `regime-chip.ts` (or the two `.tags` mounts from V239-14 if the finding is there), re-run the touched spec (`npx ng test --include <spec>`), rebuild (`npm run build`), restart `admin_ui.py`, and re-run the audit until it exits 0. A finding outside the banner, the chip and their mounts that also appears on `main` without this branch is pre-existing: list it in your report and do not fix it here.

- [ ] **Step 9: Look at the three surfaces once (at most 4 image reads)**

```bash
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --out <scratchpad>/v239-shots --path /dashboard --widths 390,1440 --clip "sb-regime-banner"
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --out <scratchpad>/v239-shots --path /dashboard --widths 390 --click "sb-regime-banner button" --clip "sb-regime-banner"
node frontend/scripts/browse.mjs shots --base http://localhost:1234 --out <scratchpad>/v239-shots --path "/trades/<closed id>" --widths 390 --clip "header.head .tags"
```

Expected, read from the four clipped images: at 390 the banner sits directly under the top bar, reads "Trend: Correction · Stress · since 2 sessions" with the `Pullback watch` chip and no inline numbers, and wraps without clipping; expanded, the number line and "Dip in an uptrend, high volatility." show under it. At 1440 it is one full-width line under the tape with the numbers inline. At 390 the trade's chip `× would skip` sits on its own line at the start of the tag row, untruncated.

- [ ] **Step 10: Remove the seed**

Run: `python <scratchpad>/v239_audit_seed.py --state <scratchpad>/v239_seed.json --undo`
Expected: `seed removed`; `node frontend/scripts/browse.mjs api --path /api/v1/market/regime` now shows `today: null` (no stored row for `D`), and the closed trade's `entry_context` has no `regime_action`. Stop `admin_ui.py`.

- [ ] **Step 11: Commit the audit fixes (skip when Step 8 passed first time)**

```bash
git add frontend/src/app/shell/regime-banner.ts frontend/src/app/workspaces/trades/why/regime-chip.ts
git commit -m "fix(v239): banner and chip pass the layout audit at 390, 768 and 1440"
```

Add `frontend/scripts/layout-audit.allow.json` (and the `.tags` mounts) to that commit only if Step 8 changed them; an allow-list entry carries its reason and today's date.

