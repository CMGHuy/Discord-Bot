# Risk reporting correctness — UI and signed weights

**Spec:** [Approved risk spec](../specs/2026-10-28-v198-risk-reporting-correctness.md)
**Index:** [Contracts, constraints and task ledger](2026-10-28-v198-risk-reporting-correctness_0-index.md)

Follow the index and part 1 response contracts. Commands below belong to implementation, not authoring. Preserve v194 hints/money/sector coverage and any merged v195 layout. Keep changes at existing component seams. Final full-suite and three-width browser layout audit belong to V198-6.

# Phase 2 — consume truthful state and preserve signed exposure

### Task V198-3: Type nullable observations and keep store/shell control state truthful
**Model:** sonnet — updates reporting models and explicit control observations without execution-policy changes.

**Files:** Modify `frontend/src/app/api/models.ts`, `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/stores/risk.store.spec.ts`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.spec.ts`; create `frontend/src/app/api/risk-state.ts`. Make the one nullable empty-check compatibility edit specified below in `frontend/src/app/workspaces/risk/risk.ts`; V198-3b owns its complete UI behavior.

**Interfaces:** Consume V198-2b Killswitch and six-domain availability, with optional later math domains. Create `unavailableKillswitch(previous: Killswitch|null, checkedAt?: string): Killswitch` for shared client-side transport failure projection. `RiskStore.killswitchOn()` and `paused()` become boolean|null. Display lists may normalize null to [] for table iteration only; `availability()` and `data()?.positions` remain authoritative for known-empty decisions. Commands always receive an explicit boolean.

- [ ] Extend the existing interfaces with the following declarations. Keep all unrelated and v194 fields. Change `Throttle.paused` and `Killswitch.on` to boolean|null, `Risk.positions/sector_heat/clusters` to their existing array type|null, add required `Risk.availability: RiskAvailability`, required `Killswitch.availability: DomainAvailability`, and optional `Killswitch.last_known: LastKnownKillswitch`. Add the three optional exclusion counters to `RiskMetric` (`excluded_count`, `invalid_date_count`, `invalid_outcome_count`); add optional `invalid_date_count` to the existing money-drawdown metric type if it does not already inherit `RiskMetric`. Their backend producers land in V198-5.

```typescript
export interface DomainAvailability {
  state: 'ok' | 'partial' | 'unavailable';
  checked_at: string;
  reason: string | null;
}
export interface RiskAvailability {
  positions: DomainAvailability;
  heat: DomainAvailability;
  sector_heat: DomainAvailability;
  clusters: DomainAvailability;
  throttle: DomainAvailability;
  killswitch: DomainAvailability;
  distribution_metrics?: DomainAvailability;
  drawdown_r?: DomainAvailability;
  drawdown_amount?: DomainAvailability;
}
export interface LastKnownKillswitch {
  on: boolean;
  reason: string | null;
  at: string | null;
  checked_at: string;
}
```

- [ ] Add status-aware fixtures and assertions to `risk.store.spec.ts`. Import `DomainAvailability` and `RiskAvailability`; define `OK` and `AVAILABILITY` as below. Add `availability: AVAILABILITY` to RESPONSE and `availability: OK` to its killswitch. Existing mutation response fixtures also carry `availability: OK`. Replace legacy initial-state assertions that equated unknown with false. Keep successful on/off assertions, command request-body tests and independent loading/toggling flags.

```typescript
const OK: DomainAvailability = {
  state: 'ok', checked_at: '2026-10-28T00:00:00+00:00', reason: null,
};
const AVAILABILITY: RiskAvailability = {
  positions: OK, heat: OK, sector_heat: OK, clusters: OK,
  throttle: OK, killswitch: OK,
};
```

Inside the existing describe, using its `respond`, `store` and `backend`:

```typescript
it('preserves null controls and unknown exposure', () => {
  const unavailable: DomainAvailability = { ...OK, state: 'unavailable', reason: 'positions_unavailable' };
  respond({ positions: null, sector_heat: null, clusters: null,
    throttle: { multiplier: null, paused: null },
    killswitch: { on: null, reason: null, at: null, availability: unavailable },
    availability: { ...AVAILABILITY, positions: unavailable, heat: unavailable } });
  expect(store.killswitchOn()).toBeNull();
  expect(store.paused()).toBeNull();
  expect(store.throttled()).toBeNull();
  expect(store.availability()?.positions.state).toBe('unavailable');
  expect(store.data()?.positions).toBeNull();
});

it('separates last observed state from current state after transport failure', () => {
  respond();
  store.load();
  backend.expectOne('/api/v1/risk').flush({}, { status: 503, statusText: 'unavailable' });
  expect(store.killswitchOn()).toBeNull();
  expect(store.killswitch()?.last_known?.on).toBe(false);
  expect(store.killswitch()?.last_known?.checked_at).toBe(OK.checked_at);
  expect(store.error()).toBeTruthy();
  expect(store.data()?.positions?.length).toBe(2);
});

it('keeps explicit commands usable before a full Risk response exists', () => {
  backend.expectOne('/api/v1/risk').flush({}, { status: 503, statusText: 'unavailable' });
  store.toggleKillswitch(true);
  const request = backend.expectOne('/api/v1/risk/killswitch');
  expect(request.request.body.on).toBe(true);
  request.flush({ killswitch: { on: true, reason: 'manual', at: null, availability: OK } });
  expect(store.killswitchOn()).toBe(true);
  expect(store.data()).toBeNull();
});

it('does not report requested state as observed after failed readback', () => {
  respond();
  store.toggleKillswitch(true);
  backend.expectOne('/api/v1/risk/killswitch').flush({ killswitch: {
    on: null, reason: null, at: null,
    availability: { ...OK, state: 'unavailable', reason: 'killswitch_unavailable' },
  } });
  expect(store.killswitchOn()).toBeNull();
  expect(store.commandError()).toContain('current state is unavailable');
  backend.expectNone('/api/v1/risk/killswitch');
});
```

- [ ] Run `npm test -- --include src/app/stores/risk.store.spec.ts` from `frontend`; expect failure for the new state projections before implementation.

- [ ] Create `api/risk-state.ts` with this projection. A failed transport does not refresh last-known checked_at and never serializes last-known as current. It uses a fresh failed-check timestamp only for current availability.

```typescript
import { Killswitch, LastKnownKillswitch } from './models';

export function unavailableKillswitch(
  previous: Killswitch | null, checkedAt = new Date().toISOString(),
): Killswitch {
  const last: LastKnownKillswitch | undefined = typeof previous?.on === 'boolean'
    ? { on: previous.on, reason: previous.reason, at: previous.at,
        checked_at: previous.availability.checked_at }
    : previous?.last_known;
  return {
    on: null, reason: null, at: null,
    availability: { state: 'unavailable', checked_at: checkedAt, reason: 'request_unavailable' },
    ...(last ? { last_known: last } : {}),
  };
}
```

- [ ] In `risk.store.ts`, add `control: Killswitch|null` to RiskSlice, initialize it to null, import the helper and `RiskAvailability`. Extend withComputed's parameters to `{ data, control }`. Replace the affected computed entries and add availability; retain existing safe-to-iterate list selectors.

```typescript
    availability: computed<RiskAvailability | null>(() => data()?.availability ?? null),
    throttled: computed<boolean | null>(() => {
      const value = data()?.throttle.multiplier;
      return value === null || value === undefined ? null : value < 1;
    }),
    paused: computed<boolean | null>(() => data()?.throttle.paused ?? null),
    killswitch: computed<Killswitch | null>(() => control()),
    killswitchOn: computed<boolean | null>(() => control()?.on ?? null),
```

Change resolve's success patch to `{ data, control: data.killswitch, loading: false, error: null }`; on its error patch additionally set `control: unavailableKillswitch(store.control())`, retaining the stale data and existing error message. Replace only the mutation subscriber callbacks with:

```typescript
          next: ({ killswitch }) => {
            const data = store.data();
            patchState(store, {
              toggling: false, control: killswitch,
              commandError: killswitch.on === null
                ? 'Command sent; current state is unavailable. Verify before relying on it.' : null,
              data: data ? { ...data, killswitch,
                availability: { ...data.availability, killswitch: killswitch.availability } } : data,
            });
          },
          error: (error: ApiError) => patchState(store, {
            toggling: false, control: unavailableKillswitch(store.control()),
            commandError: error.code === 'unavailable'
              ? 'Could not confirm the requested killswitch state. Current state is unavailable.'
              : error.message,
          }),
```

Update obsolete comments claiming missing multiplier means 1 or missing killswitch means off. In `risk.ts`'s asyncInputs expression replace `data.positions.length === 0` with `data.positions?.length === 0` so nullable wire types compile; V198-3b strengthens this with domain availability and applies panel gates.

- [ ] In `shell.ts`, import Killswitch and unavailableKillswitch; replace the writable `killswitchOn = signal(false)` with `protected readonly killObservation = signal<Killswitch|null>(null)` and `protected readonly killswitchOn = computed(() => this.killObservation()?.on ?? null)`. Replace only `refreshKillswitch`'s callbacks:

```typescript
      next: ({ killswitch }) => this.killObservation.set(killswitch),
      error: () => this.killObservation.set(unavailableKillswitch(this.killObservation())),
```

In `shell.html`, replace the existing engaged-only strip condition with explicit current-state branches. Keep its existing layout position after the header. Before the first observation, render no assertion of clear/engaged; a failed request has an observation with unavailable status.

```html
    @if (killswitchOn() === true) {
      <div class="killswitch-strip" role="alert">KILLSWITCH ENGAGED</div>
    } @else if (killObservation()?.availability?.state === 'unavailable') {
      <div class="killswitch-strip" role="status">
        KILLSWITCH STATE UNAVAILABLE
        @if (killObservation()?.last_known; as last) {
          <span>Last observed {{ last.on ? 'engaged' : 'clear' }} at {{ last.checked_at }} — stale</span>
        }
      </div>
    }
```

- [ ] Replace the shell test that directly sets a protected boolean signal with this HTTP-driven test inside its existing describe. Add the HttpTestingController import if absent. The first successful false response still produces no engaged strip; the later failure never silently leaves the old false signal current.

```typescript
it('shows unknown shell state after a fresh failed read, with a stale observation', () => {
  const f = TestBed.createComponent(Shell);
  f.detectChanges();
  const http = TestBed.inject(HttpTestingController);
  const ok = { state: 'ok', checked_at: '2026-10-28T00:00:00+00:00', reason: null };
  http.expectOne('/api/v1/risk/killswitch').flush({ killswitch: {
    on: false, reason: null, at: null, availability: ok,
  } });
  f.detectChanges();
  expect(f.nativeElement.querySelector('.killswitch-strip')).toBeNull();
  (f.componentInstance as unknown as { refreshKillswitch(): void }).refreshKillswitch();
  http.expectOne('/api/v1/risk/killswitch').flush({}, { status: 503, statusText: 'unavailable' });
  f.detectChanges();
  const strip = f.nativeElement.querySelector('.killswitch-strip') as HTMLElement;
  expect(strip.getAttribute('role')).toBe('status');
  expect(strip.textContent).toContain('STATE UNAVAILABLE');
  expect(strip.textContent).toContain('Last observed clear');
  expect(strip.textContent).toContain('stale');
  http.expectNone('/api/v1/risk/killswitch');
});
```

Retain engaged banner coverage by flushing an HTTP success with on:true and availability:ok in a separate existing engaged test; its role stays alert. Do not synthesize a command to recover from a read failure.

- [ ] Run `npm test -- --include src/app/stores/risk.store.spec.ts` and `npm test -- --include src/app/shell/shell.spec.ts` from frontend. Resolve only those failures; the complete UI is verified in V198-3b and the plan's single full frontend run remains final. Stage only the named files and commit `fix(risk-ui): preserve unknown control observations` after repository status checks. No version bump yet.

### Task V198-3b: Render unknown/partial/stale Risk domains and explicit actions
**Model:** sonnet — adapts existing panels and confirmation flow to finalized nullable observations.

**Files:** Modify `frontend/src/app/workspaces/risk/risk.ts` and `frontend/src/app/workspaces/risk/risk.spec.ts`. No new component architecture or independent Risk spec file.

**Interfaces:** Consume V198-3 availability/current-control selectors. Create component-local `domainProblem(key: keyof RiskAvailability, label: string): string|null`, explicit `requestedOn` signal, `ask(on: boolean)` and guarded `confirm()`. Later math fields are optional until V198-4/5 produce them. Preserve existing phone drawer, hints, pagination, configured benchmark and account-currency money labels.

- [ ] In risk.spec.ts import DomainAvailability/RiskAvailability; add the same typed OK/AVAILABILITY fixture constants used in V198-3. Add `availability: AVAILABILITY` and a complete killswitch with availability:OK to `payload()`. Existing fixtures overriding only killswitch must add its availability. Keep successful known-empty cases. Add these cases using the existing seed/payload helpers and device providers:

```typescript
for (const device of ['lg', 'sm', 'xs'] as const) {
  it(`renders unavailable domains without a false empty-book claim at ${device}`, async () => {
    const { fixture, backend } = seed([{ provide: ViewportService,
      useValue: { viewport: signal(device), isPhone: signal(device === 'xs'),
        isNarrow: signal(device !== 'lg') } }]);
    fixture.detectChanges();
    const unavailable: DomainAvailability = { ...OK, state: 'unavailable', reason: 'positions_unavailable' };
    backend.expectOne('/api/v1/risk').flush(payload({
      positions: null, sector_heat: null, clusters: null,
      heat: { open_pct: null, cap_pct: 6, utilisation_pct: null },
      throttle: { multiplier: null, paused: null },
      killswitch: { on: null, reason: null, at: null, availability: unavailable },
      availability: { positions: unavailable, heat: unavailable, sector_heat: unavailable,
        clusters: unavailable, throttle: unavailable, killswitch: unavailable },
    }));
    await fixture.whenStable(); fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('Positions: unavailable');
    expect(root.textContent).toContain('Heat: unavailable');
    expect(root.textContent).toContain('Throttle: unavailable');
    expect(root.textContent).not.toContain('No open risk');
    expect(root.textContent).not.toContain('Sizing unthrottled');
    expect(root.textContent).not.toContain('free to open new positions');
    expect(root.querySelector('[role="status"]')).not.toBeNull();
  });
}

for (const on of [true, false]) {
  it(`requests explicit ${on ? 'engage' : 'release'} from unknown state`, async () => {
    installDialogPolyfill();
    const { fixture, backend } = seed();
    fixture.detectChanges();
    backend.expectOne('/api/v1/risk').flush(payload({ killswitch: {
      on: null, reason: null, at: null,
      availability: { ...OK, state: 'unavailable', reason: 'killswitch_unavailable' },
      last_known: { on: !on, reason: null, at: null, checked_at: OK.checked_at },
    } }));
    await fixture.whenStable(); fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const label = on ? 'Engage killswitch' : 'Release killswitch';
    const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button'))
      .find((candidate) => candidate.textContent?.trim() === label)!;
    expect(button.disabled).toBe(false);
    button.click(); fixture.detectChanges();
    backend.expectNone('/api/v1/risk/killswitch');
    expect(root.querySelector('sb-confirm-dialog')).not.toBeNull();
    (fixture.componentInstance as unknown as { confirm(): void }).confirm();
    const request = backend.expectOne('/api/v1/risk/killswitch');
    expect(request.request.body.on).toBe(on);
    request.flush({ killswitch: { on, reason: null, at: null, availability: OK } });
    await fixture.whenStable(); fixture.detectChanges();
    backend.expectNone('/api/v1/risk/killswitch');
  });
}
```

Add the following focused partial/stale/counter case using `render` (the existing helper) and fixtures. It asserts real production binding text rather than a source-code substring:

```typescript
it('keeps position identities while explaining incomplete R and sector coverage', async () => {
  const fixture = await render({
    positions: [{ ...FRACTIONAL_BOOK[0], risk_pct: null }],
    heat: { open_pct: null, cap_pct: 6, utilisation_pct: null },
    sector_heat: [], unmapped_count: 1,
    availability: { ...AVAILABILITY,
      heat: { ...OK, state: 'unavailable', reason: 'invalid_balance' },
      sector_heat: { ...OK, state: 'partial', reason: 'sector_mapping_incomplete' },
      drawdown_r: { ...OK, state: 'partial', reason: 'invalid_closed_records' } },
    metrics: { ...DEFAULT_METRICS, max_drawdown_r: {
      value: 2, n: 3, excluded_count: 2, invalid_date_count: 1, invalid_outcome_count: 1,
    } },
  });
  const root = fixture.nativeElement as HTMLElement;
  expect(root.textContent).toContain(FRACTIONAL_BOOK[0].ticker);
  expect(root.textContent).toContain('1 invalid close dates');
  expect(root.textContent).toContain('1 invalid outcomes');
  expect(root.textContent).toContain('Quote returns');
  expect(root.textContent).toContain('historical FX returns excluded');
});
```

- [ ] Run `npm test -- --include src/app/workspaces/risk/risk.spec.ts`; observe the new unavailable/action assertions failing.

- [ ] Import `RiskAvailability` and change the component's small status/control helpers as follows. Keep asking's existing signal and the existing confirm dialog. Last-known is display information only. Capture desired state when opening the dialog so a response arriving while it is open cannot reverse the pending request.

```typescript
  protected readonly requestedOn = signal<boolean | null>(null);

  protected domainProblem(key: keyof RiskAvailability, label: string): string | null {
    if (this.store.error()) return `${label}: last observation is stale.`;
    const status = this.store.availability()?.[key];
    if (!status) return `${label}: unavailable`;
    if (status.state === 'ok') return null;
    return `${label}: ${status.state === 'partial' ? 'coverage incomplete' : 'unavailable'}`;
  }

  protected readonly positionsKnown = computed(() =>
    this.store.data()?.positions != null && this.store.availability()?.positions.state === 'ok',
  );

  protected readonly sectorProblem = computed(() =>
    this.domainProblem('sector_heat', 'Sector heat')
      ?? unmappedNote(this.store.unmappedCount(), this.store.positions().length),
  );

  protected readonly async = computed(() => asyncInputs(this.store, {
    isEmpty: (data) => data.positions?.length === 0
      && (['positions', 'heat', 'sector_heat', 'clusters'] as const)
        .every((key) => data.availability?.[key]?.state === 'ok'),
  }));

  protected readonly announce = computed(() => this.positionsKnown()
    ? `${this.store.positions().length} open positions`
    : this.store.empty() ? null : 'Positions: unavailable');

  protected readonly killswitchDetail = computed(() => {
    const kill = this.store.killswitch();
    if (kill?.on === null && kill.last_known) {
      const last = kill.last_known;
      return `Last observed ${last.on ? 'engaged' : 'clear'} at ${dateTime(last.checked_at)} — stale`;
    }
    if (kill?.on !== true) return null;
    return [kill.at ? `Engaged ${dateTime(kill.at)}` : null,
      kill.reason ? `Reason: ${kill.reason}` : null].filter(Boolean).join(' · ') || null;
  });

  protected readonly dialogTitle = computed(() => this.requestedOn() === false
    ? 'Release the killswitch' : 'Engage the killswitch');
  protected readonly dialogConfirm = computed(() => this.requestedOn() === false ? 'Release' : 'Engage');
  protected readonly dialogConsequence = computed(() => {
    const action = this.requestedOn() === false
      ? 'Release this killswitch. Other controls may still prevent new positions.'
      : 'Engage this killswitch to stop new positions. This does not close existing trades.';
    const coverage = this.positionsKnown()
      ? `${this.store.positions().length} open positions are reported.`
      : 'Open-position coverage is unavailable.';
    return `${action} ${coverage} Check the returned state before relying on the change.`;
  });

  protected ask(on: boolean): void {
    this.requestedOn.set(on);
    this.asking.set(true);
  }

  protected confirm(): void {
    const on = this.requestedOn();
    if (on === null) return;
    this.store.toggleKillswitch(on);
    this.asking.set(false);
    this.requestedOn.set(null);
  }
```

For sector partial coverage, keep the v194 unmapped sentence visible beneath the status instead of replacing it: add `protected readonly unmappedProblem = computed(() => unmappedNote(this.store.unmappedCount(), this.store.positions().length))` and render it only when the sector state is partial. A complete map still uses the original known-sector rows and hints.

- [ ] Replace the killswitch value/explanation branches and the single action button with explicit states, preserving surrounding panel/command-error/dialog structure:

```html
<span class="kill-value" [class.engaged]="store.killswitchOn() === true" role="status">
  {{ store.killswitchOn() === null ? 'Unavailable' : store.killswitchOn() ? 'ENGAGED' : 'Clear' }}
</span>
<p class="kill-explain">
  @if (store.killswitchOn() === null) {
    Current killswitch state is unavailable. Choose an explicit action if needed.
  } @else if (store.killswitchOn() === true) {
    The bot is not opening new positions. Open trades remain monitored.
  } @else {
    This killswitch is clear. Other risk controls may still prevent new positions.
  }
</p>
```

```html
<div class="kill-actions">
  @if (store.killswitchOn() !== true) {
    <button sb-button variant="danger" type="button" class="sb-hit"
      [loading]="store.toggling()" [disabled]="store.toggling()" (click)="ask(true)">
      Engage killswitch
    </button>
  }
  @if (store.killswitchOn() !== false) {
    <button sb-button variant="secondary" type="button" class="sb-hit"
      [loading]="store.toggling()" [disabled]="store.toggling()" (click)="ask(false)">
      Release killswitch
    </button>
  }
</div>
```

Keep `killswitchDetail()` displayed beneath the explanation. Add `.kill-actions { display: flex; flex-wrap: wrap; gap: var(--space-8); }` to the existing component styles. Never disable these actions merely because `store.empty()` or a read failed. Existing confirmation remains mandatory in both directions.

- [ ] Integrate domain status at these exact template seams; retain the panel/table content unless a specific unavailable domain makes its empty fallback false:

  - At the start of Portfolio heat, add `<p role="status" class="section-help">{{ domainProblem('heat', 'Heat') }}</p>` guarded by that method's nonnull result. Existing null meter behavior remains. Before the throttle badges, render the analogous `domainProblem('throttle', 'Throttle')` status. Change “Sizing unthrottled” condition to `store.paused() === false && store.throttled() === false && !domainProblem('throttle', 'Throttle')`; null never satisfies it.
  - Inside Exposure by position, wrap the existing unchanged sb-data-table in `@if (positionsKnown()) { ... } @else { <p role="status" class="section-help">Positions: unavailable</p> }`. This prevents its empty-state component from inventing zero exposure. Retained identities with unknown heat still render.
  - Sector heat already receives `[problem]="sectorProblem()"`; render unmappedProblem when status is partial. Its existing “No sector exposure” fallback runs only when sectorProblem is null, so failed mapping cannot become zero exposure.
  - Before cluster rows, render `domainProblem('clusters', 'Clusters')` with role status. Keep known rows for partial results. Gate “No correlated clusters” with `!domainProblem('clusters', 'Clusters')`.
  - Change correlation panel heading to “Underlying-asset correlation”. Its help names daily quote returns. Gate its “Not enough open positions” fallback on known positions and a non-unavailable distribution status; unavailable coverage instead displays “Correlation data unavailable.” Keep every matrix value unchanged.

- [ ] Unknown per-position risk must not sum into a zero Risk % footer. Add this exported pure helper beside existing formatting helpers and use it in that column's footer and footerHint, replacing both `(risk_pct ?? 0)` reductions. Keep the v194 share footer unchanged.

```typescript
export function knownRiskTotal(rows: RiskPosition[]): number | null {
  return rows.some((row) => row.risk_pct === null)
    ? null : rows.reduce((sum, row) => sum + row.risk_pct!, 0);
}
```

Footer becomes `(rows) => riskPct(knownRiskTotal(rows))`; footerHint computes `exactRiskText(knownRiskTotal(rows))`. Add a direct test `expect(knownRiskTotal([{ ...FRACTIONAL_BOOK[0], risk_pct: null }])).toBeNull()` and preserve existing exact-small-total tests.

- [ ] In the metrics panel before the strip, add the visible basis paragraph “Quote returns; entry notionals valued in account currency; historical FX returns excluded”. Render distribution status only when that optional domain is present. Render optional drawdown domain statuses and counters without suppressing valid trade metrics on market failure. Add these two computed strings:

```typescript
  protected readonly rCoverage = computed(() => {
    const metric = this.store.metrics()?.max_drawdown_r;
    if (!metric?.excluded_count) return null;
    return `Closed R sample excludes ${metric.excluded_count}: ${metric.invalid_date_count ?? 0} invalid close dates, ${metric.invalid_outcome_count ?? 0} invalid outcomes.`;
  });
  protected readonly moneyDateCoverage = computed(() => {
    const count = this.store.metrics()?.max_drawdown_amount?.invalid_date_count ?? 0;
    return count ? `Money drawdown excludes ${count} invalid close dates.` : null;
  });
```

Render each nonnull string in `<p class="section-help" role="status">`. Keep existing fx_missing_count note, metric population labels and benchmark_symbol label. A missing optional domain before its producing task lands does not claim success or show a fabricated count.

- [ ] Run `npm test -- --include src/app/workspaces/risk/risk.spec.ts`. Preserve device-class assertions, exact-hint reachability, known-empty and unknown states, command confirmation, partial coverage and money/R labels. The final task performs the real phone/tablet/desktop browser audit; do not add allow-list exceptions for hidden hints. Stage the two files and commit `fix(risk-ui): render unavailable coverage and explicit actions` after status checks.

### Task V198-4: Build signed common-currency gross-normalized weights
**Model:** sonnet — implements a bounded Risk read-model calculation with explicit coverage errors.

**Files:** Create `swingbot/admin/api_v1/risk_read_model.py` and `tests/admin/test_risk_read_model.py`. The existing admin test suite owns the new test file; no new directory or suite is needed.

**Interfaces:** `signed_weights(open_trades: list[dict], *, on: date, account: str|None=None) -> tuple[dict[str,float], str|None]`, plus `complete_bars(symbols: list[str], bars: dict) -> bool` for V198-4b. Both use actual bullish/bearish directions; no long default. Common currency is valued once at the supplied date. Zero-net tickers remain keys. All exposure contributes to the gross denominator before netting. No modification to general portfolio_returns or FX providers.

- [ ] Add synthetic tests with the real shared FX seam monkeypatched; never fetch a quote or production row. Reuse these helpers in the later chronology tests without changing their names.

```python
from datetime import date

import numpy as np
import pandas as pd
import pytest

import swingbot.admin.app  # initialize the API package as existing admin fixtures do
from swingbot.admin.api_v1 import risk_read_model as model
from swingbot.core.marketdata import fx

DAY = date(2026, 10, 28)


def position(ticker="AAA", direction="bullish", entry=100.0, shares=1.0):
    return {"ticker": ticker, "direction": direction, "entry": entry, "shares": shares}


@pytest.fixture
def currency(monkeypatch):
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: "EUR")
    monkeypatch.setattr(fx, "fx_rate", lambda source, target, on: 1.0)


@pytest.mark.parametrize("rows, expected", [
    ([position()], {"AAA": 1.0}),
    ([position(direction="bearish")], {"AAA": -1.0}),
    ([position(shares=3), position("BBB", "bearish")], {"AAA": 0.75, "BBB": -0.25}),
    ([position(), position(direction="bearish")], {"AAA": 0.0}),
    ([position(shares=3), position(direction="bearish")], {"AAA": 0.5}),
    ([], {}),
])
def test_gross_weights_preserve_direction_and_netting(currency, rows, expected):
    weights, reason = model.signed_weights(rows, on=DAY)
    assert reason is None
    assert weights == pytest.approx(expected)


def test_cross_currency_weights_share_one_valuation_date(currency, monkeypatch):
    calls = []
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: "USD" if ticker == "AAA" else "EUR")
    def rate(source, target, on):
        calls.append((source, target, on))
        return 2.0 if source == "USD" else 1.0
    monkeypatch.setattr(fx, "fx_rate", rate)
    weights, reason = model.signed_weights([position(shares=2), position("BBB", "bearish")], on=DAY)
    assert reason is None
    assert weights == pytest.approx({"AAA": 0.8, "BBB": -0.2})
    assert calls == [("USD", "EUR", DAY), ("EUR", "EUR", DAY)]


@pytest.mark.parametrize("field,value,reason", [
    ("direction", None, "invalid_direction"), ("direction", "long", "invalid_direction"),
    ("entry", 0, "invalid_position"), ("entry", float("nan"), "invalid_position"),
    ("shares", -1, "invalid_position"), ("shares", float("inf"), "invalid_position"),
    ("shares", "bad", "invalid_position"), ("ticker", "", "invalid_position"),
])
def test_invalid_exposure_never_becomes_a_partial_normalized_book(currency, field, value, reason):
    bad = {**position("BBB"), field: value}
    assert model.signed_weights([position(), bad], on=DAY) == ({}, reason)


@pytest.mark.parametrize("rate,reason", [(None, "missing_fx"), (0, "invalid_fx"),
                                        (-1, "invalid_fx"), (float("nan"), "invalid_fx")])
def test_bad_fx_is_not_parity(currency, monkeypatch, rate, reason):
    monkeypatch.setattr(fx, "fx_rate", lambda *args: rate)
    assert model.signed_weights([position()], on=DAY) == ({}, reason)


def test_missing_quote_currency_is_unavailable(currency, monkeypatch):
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: None)
    assert model.signed_weights([position()], on=DAY) == ({}, "missing_quote_currency")


def test_short_quote_returns_have_negative_beta(currency):
    from swingbot.core.analytics import risk_metrics as rm
    closes = 100 * np.cumprod(1 + 0.01 * np.sin(np.arange(100)))
    frame = pd.DataFrame({"Close": closes}, index=pd.date_range("2026-01-01", periods=100))
    weights, _ = model.signed_weights([position(direction="bearish")], on=DAY)
    returns = rm.portfolio_returns(weights, {"AAA": frame})
    benchmark = rm.portfolio_returns({"AAA": 1.0}, {"AAA": frame})
    assert rm.beta_vs(returns, benchmark) == pytest.approx(-1.0)


def test_bar_coverage_requires_zero_net_names_too():
    frame = pd.DataFrame({"Close": [100.0, 101.0]})
    assert model.complete_bars(["AAA", "BBB"], {"AAA": frame}) is False
    assert model.complete_bars(["AAA"], {"AAA": frame}) is True
    assert model.complete_bars(["AAA"], {"AAA": pd.DataFrame({"Close": [100.0, np.nan]})}) is False
```

- [ ] Run `python scripts/dev/testrun.py file tests/admin/test_risk_read_model.py`; expect missing module/helpers before implementation. These synthetic cases do not intentionally access a database; if suite conftest does, complete the replica prerequisite first.

- [ ] Create the read-model module with these implementations. Date is explicit, FX uses its existing minor-unit handling, and each failure returns a sanitized reason with no partial weights. The helper neither owns a price cache nor reads account configuration itself.

```python
"""Risk reporting selection and weighting; never a trading-policy input."""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from swingbot.core.marketdata import fx


class _WeightError(ValueError):
    pass


def _positive(value, reason: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _WeightError(reason) from exc
    if isinstance(value, bool) or not math.isfinite(result) or result <= 0:
        raise _WeightError(reason)
    return result


def _quote_rate(ticker: str, account: str, on: date) -> float:
    try:
        quote = fx.quote_currency_code(ticker)
    except Exception as exc:
        raise _WeightError("missing_quote_currency") from exc
    if not quote:
        raise _WeightError("missing_quote_currency")
    try:
        rate = fx.fx_rate(quote, account, on)
    except Exception as exc:
        raise _WeightError("missing_fx") from exc
    if rate is None:
        raise _WeightError("missing_fx")
    return _positive(rate, "invalid_fx")


def _position_notional(trade: dict, account: str, on: date) -> tuple[str, float, float]:
    ticker = trade.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise _WeightError("invalid_position")
    ticker = ticker.strip().upper()
    sign = {"bullish": 1.0, "bearish": -1.0}.get(trade.get("direction"))
    if sign is None:
        raise _WeightError("invalid_direction")
    entry = _positive(trade.get("entry"), "invalid_position")
    shares = _positive(trade.get("shares"), "invalid_position")
    value = _positive(entry * shares * _quote_rate(ticker, account, on), "invalid_position")
    return ticker, value, sign


def signed_weights(open_trades: list[dict], *, on: date,
                   account: str | None = None) -> tuple[dict[str, float], str | None]:
    if not open_trades:
        return {}, None
    try:
        account = account if account is not None else fx.account_currency_code()
        gross = 0.0
        signed: dict[str, float] = {}
        for trade in open_trades:
            ticker, notional, sign = _position_notional(trade, account, on)
            gross += notional
            signed[ticker] = signed.get(ticker, 0.0) + sign * notional
        gross = _positive(gross, "invalid_position")
        if any(not math.isfinite(value) for value in signed.values()):
            raise _WeightError("invalid_position")
        return {ticker: value / gross for ticker, value in signed.items()}, None
    except _WeightError as exc:
        return {}, str(exc)
    except Exception:
        return {}, "invalid_position"


def _valid_frame(frame) -> bool:
    try:
        close = frame["Close"]
        return not close.empty and bool(np.isfinite(close).all()) and bool((close > 0).all())
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def complete_bars(symbols: list[str], bars: dict) -> bool:
    return all(_valid_frame(bars.get(symbol)) for symbol in symbols)
```

- [ ] Run the narrow test file and `python scripts/dev/complexity_gate.py`; keep every helper/closure below 15. Review the gross denominator with same-ticker hedges and minor units; do not renormalize signed exposure. Stage the two new files and commit `fix(risk): preserve direction in common-currency weights`. V198-4b wires the tested calculation into the API; no full suite or backtest is authorized by this task.

### Task V198-4b: Integrate complete distribution coverage without losing trade metrics
**Model:** sonnet — wires the tested read-model into independent Risk market-data calculations.

**Files:** Modify `swingbot/admin/api_v1/risk.py` and `tests/admin/test_api_v1_risk.py`, including V198-2b's `projection_state` metrics stub. If complexity baseline shrink is reported, update `scripts/dev/complexity_baseline.json` using its tool. Do not change portfolio_returns, correlation_matrix, FX stores or the global r_multiples helper.

**Interfaces:** `_risk_metrics_and_correlation() -> tuple[dict, dict, dict]` now returns metrics, underlying-asset correlation and availability mapping. Create `_distribution_metrics(open_trades: list|None, benchmark: str, checked: str) -> tuple[dict, dict, dict]`; math-only internals are not shared contracts. V198-5 extends the third mapping with drawdown domains while preserving the independently computed market block. Valuation date is the UTC date of checked; one date for every position in the calculation.

- [ ] Add integration tests in the existing API file. Use the FX seam and synthetic closes. These fixtures access only injected data; the file's pre-existing database tests still require the shared replica ritual before execution.

```python
@pytest.fixture
def distribution_inputs(monkeypatch):
    import numpy as np
    from swingbot.admin.api_v1 import risk
    from swingbot.core.marketdata import fx
    closes = 100 * np.cumprod(1 + 0.01 * np.sin(np.arange(100)))
    frame = pd.DataFrame({"Close": closes}, index=pd.date_range("2026-01-01", periods=100))
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: "EUR")
    monkeypatch.setattr(fx, "fx_rate", lambda *args: 1.0)
    monkeypatch.setattr(risk, "_risk_bars", lambda symbols: {symbol: frame for symbol in symbols})
    return risk, frame


@pytest.mark.parametrize("direction,beta", [("bullish", 1.0), ("bearish", -1.0)])
def test_distribution_beta_preserves_position_direction(distribution_inputs, direction, beta):
    risk, _ = distribution_inputs
    trade = {**_open_trade("direction"), "direction": direction}
    metrics, corr, availability = risk._distribution_metrics([trade], "SPY", "2026-10-28T00:00:00+00:00")
    assert metrics["beta_spy"]["value"] == pytest.approx(beta)
    assert availability["distribution_metrics"]["state"] == "ok"
    assert corr["labels"] == ["AAPL"]


def test_offset_book_is_not_renormalized_into_nonzero_risk(distribution_inputs):
    risk, _ = distribution_inputs
    long = _open_trade("long")
    short = {**long, "id": "short", "direction": "bearish"}
    metrics, corr, availability = risk._distribution_metrics([long, short], "SPY", "2026-10-28T00:00:00+00:00")
    for name in ("var_95", "expected_shortfall_95", "annualised_vol", "beta_spy"):
        assert metrics[name]["value"] is None
    assert corr["labels"] == ["AAPL"]
    assert availability["distribution_metrics"]["state"] == "ok"


def test_missing_bars_are_unavailable_not_partial_weights(distribution_inputs, monkeypatch):
    risk, frame = distribution_inputs
    monkeypatch.setattr(risk, "_risk_bars", lambda symbols: {"SPY": frame})
    metrics, _, availability = risk._distribution_metrics([_open_trade("missing")], "SPY", "2026-10-28T00:00:00+00:00")
    assert metrics["var_95"]["value"] is None
    assert availability["distribution_metrics"]["reason"] == "incomplete_bars"


def test_signed_exposures_do_not_flip_asset_correlation(distribution_inputs):
    risk, _ = distribution_inputs
    rows = [_open_trade("long", ticker="AAA"),
            {**_open_trade("short", ticker="BBB"), "direction": "bearish"}]
    _, corr, _ = risk._distribution_metrics(rows, "SPY", "2026-10-28T00:00:00+00:00")
    assert corr["values"][0][1] == pytest.approx(1.0)


def test_failed_market_data_preserves_trade_derived_metrics(distribution_inputs, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, status=None, **kw:
                        [_open_trade("open")] if status == "open" else [_closed_trade("closed")])
    monkeypatch.setattr(risk, "_max_drawdown_amount", lambda closed: {"value": 0, "n": 1, "fx_missing_count": 0})
    monkeypatch.setattr(risk, "_risk_bars", unavailable_read)
    metrics, _, availability = risk._risk_metrics_and_correlation()
    assert metrics["max_drawdown_r"]["n"] == 1
    assert metrics["max_drawdown_amount"]["n"] == 1
    assert availability["distribution_metrics"]["reason"] == "market_data_unavailable"
```

Update the earlier `projection_state` fixture's metrics lambda from `({}, {"labels": [], "values": []})` to `({}, {"labels": [], "values": []}, {})`. Keep its independent controller tests working; they do not need invented math status. Add this missing-FX API assertion; preserve existing benchmark-label and market-failure tests.

```python
def test_distribution_missing_fx_is_explicit(distribution_inputs, monkeypatch):
    from swingbot.core.marketdata import fx
    risk, _ = distribution_inputs
    monkeypatch.setattr(fx, "fx_rate", lambda *args: None)
    metrics, _, availability = risk._distribution_metrics(
        [_open_trade("missing-fx")], "SPY", "2026-10-28T00:00:00+00:00")
    assert metrics["var_95"]["value"] is None
    assert availability["distribution_metrics"]["reason"] == "missing_fx"
```

- [ ] Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`, observe new missing-helper/contract failures, then add the following helpers in risk.py. Import `risk_read_model` locally where shown. Preserve configured benchmark and correlation semantics. Zero variance produces null beta locally, rather than changing the shared beta helper's unrelated consumers.

```python
_DISTRIBUTION_KEYS = ("var_95", "expected_shortfall_95", "annualised_vol", "beta_spy")


def _empty_distribution() -> dict:
    return {**{key: _metric(None, 0) for key in _DISTRIBUTION_KEYS}, "as_of": None}


def _distribution_status(checked: str, reason: str | None) -> dict:
    return {"distribution_metrics": {"state": "unavailable" if reason else "ok",
                                      "checked_at": checked, "reason": reason}}


def _asset_symbols(rows: list) -> list[str]:
    return sorted({str(row["ticker"]).strip().upper() for row in rows
                   if isinstance(row, dict) and isinstance(row.get("ticker"), str) and row["ticker"].strip()})


def _asset_correlation(symbols: list[str], bars: dict) -> dict:
    from swingbot.core.analytics import risk_metrics as rm
    try:
        labels, values = rm.correlation_matrix(symbols, bars)
        return {"labels": labels, "values": values}
    except Exception:
        return {"labels": symbols, "values": []}


def _market_values(weights: dict, bars: dict, benchmark: str) -> dict:
    from swingbot.core.analytics import risk_metrics as rm
    returns = rm.portfolio_returns(weights, bars)
    benchmark_returns = rm.portfolio_returns({benchmark: 1.0}, bars)
    count = len(returns)
    volatility = rm.annualised_vol(returns)
    beta = rm.beta_vs(returns, benchmark_returns) if volatility is not None else None
    return {
        "var_95": _metric(rm.value_at_risk(returns), count),
        "expected_shortfall_95": _metric(rm.expected_shortfall(returns), count),
        "annualised_vol": _metric(volatility, count),
        "beta_spy": _metric(beta, len(returns.align(benchmark_returns, join="inner")[0])),
        "as_of": returns.index[-1].strftime("%Y-%m-%d") if count else None,
    }


def _covered_distribution(weights: dict, symbols: list, bars: dict,
                          benchmark: str, checked: str) -> tuple:
    from .risk_read_model import complete_bars
    if not complete_bars(sorted(set(symbols) | {benchmark}), bars):
        return _empty_distribution(), _distribution_status(checked, "incomplete_bars")
    try:
        values = _market_values(weights, bars, benchmark)
    except Exception:
        return _empty_distribution(), _distribution_status(checked, "market_data_unavailable")
    reason = None if values["as_of"] is not None else "incomplete_bars"
    return values, _distribution_status(checked, reason)


def _distribution_metrics(open_trades: list | None, benchmark: str, checked: str) -> tuple[dict, dict, dict]:
    from .risk_read_model import signed_weights
    if open_trades is None:
        return _empty_distribution(), {"labels": [], "values": []}, _distribution_status(checked, "positions_unavailable")
    if not open_trades:
        return _empty_distribution(), {"labels": [], "values": []}, _distribution_status(checked, None)
    symbols = _asset_symbols(open_trades)
    weights, reason = signed_weights(open_trades, on=datetime.fromisoformat(checked).date())
    try:
        bars = _risk_bars(sorted(set(symbols) | {benchmark}))
    except Exception:
        return _empty_distribution(), {"labels": symbols, "values": []}, _distribution_status(checked, reason or "market_data_unavailable")
    correlation = _asset_correlation(symbols, bars)
    if reason:
        return _empty_distribution(), correlation, _distribution_status(checked, reason)
    values, availability = _covered_distribution(weights, symbols, bars, benchmark, checked)
    return values, correlation, availability
```

- [ ] Replace only the old notional/weights and market-data tail in `_risk_metrics_and_correlation`, starting at the comment before its `notional: dict[str, float]` try block through the function's final exception return. Keep the earlier closed-trade fetch, independent R guard, money metric and null_metrics population unchanged until V198-5. Replace the old open-trade exception fallback `open_trades = []` with `open_trades = None`; remove `or []` from the successful open read so a malformed None response does not become a known-empty book. Use this new tail and update the signature/docstring for the third result:

```python
    checked = datetime.now(timezone.utc).isoformat()
    market, correlation, availability = _distribution_metrics(open_trades, benchmark, checked)
    return {**null_metrics, **market}, correlation, availability
```

The closed-metric domain is still independent; no market helper receives or modifies its population. In `get_risk`, replace the two-result cache unpacking with `metrics, correlation, metric_availability = _cached("metrics", _risk_metrics_and_correlation)`. Its response availability entry becomes:

```python
        "availability": {**state.get("availability", {}), **metric_availability,
                         "killswitch": kill["availability"]},
```

This merges copies; it never annotates or pops from cached objects. Retain benchmark_symbol in null_metrics so successful and unavailable paths carry the configured label. Update stale docstrings claiming positive weights or `_positions` independently reads TradeLog.

- [ ] Run the affected API test file narrowly after the replica prerequisite. Check long/short/hedged cases, independent R/money survival, missing FX/bars and configured benchmark. Run `python scripts/dev/complexity_gate.py`; because the old large function shrinks, apply `--update` only if requested by the gate, then rerun it. No backtest, full suite or behavior change to shared analytics is needed. Stage only the named files and commit `fix(risk): expose complete signed distribution coverage`. V198-5 may now extend the third availability result with its date/outcome counts.

