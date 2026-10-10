# v151 Plan detail page and the shared "Why" panel: Part 2, store and Why components

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V151-9:" -A 400 docs/superpowers/plans/2026-10-10-v151-plan-detail-why-panel_2-store-and-why-components.md`.

**Bump:** ui minor · bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-09-v151-plan-detail-why-panel-design.md`](../specs/2026-10-09-v151-plan-detail-why-panel-design.md)

Global constraints, the decisions this part relies on (5, 8, 9 and the wire contract), the task ledger and `## Parallelisation` live in the index: [`2026-10-10-v151-plan-detail-why-panel_0-index.md`](2026-10-10-v151-plan-detail-why-panel_0-index.md). Every task below implicitly includes those constraints. The short version:

- v146 keys (`confidence_points`, `confidence_unevaluated`) are passed through, never computed. Absent means `null` / `[]` in the store. The page must work on records written before v146.
- Empty is a measured answer: an empty `gates` list renders `—`, an empty `calendar` renders `None in the window`. Gate rows are never hidden.
- Verbatim copy: heading `Gate margins (vs today's thresholds)`; caveat `Margins are measured against today's thresholds, not the ones in force when this plan was issued.` (always visible, no toggle); "off" chip tooltip `off in current config`; "unevaluated" chip tooltip `no data — neutral points awarded`; paper line `Paper plan — this page places no orders.`
- The components in `frontend/src/app/workspaces/trades/why/` are **not** wired into any page in this part. V151-15 (trade page) and V151-16 (plan page) compose them.
- Frontend gate specs that scan every call site (`ui/primitives.spec.ts`, `ui/spacing.spec.ts`) apply to the new files. Do not define the classes `.pos`, `.neg`, `.muted`, `.head`, `.row-link`, `.note` or `.chips` in a component's `styles`; use the global `.pos` / `.neg` / `.muted` / `.num` / `.section-help` from `styles.css`. Declare no hex colour and no outer margin on a selector applied to `sb-panel`. Reference only CSS custom properties that already exist (the ones used in `trade-detail.ts`'s styles are safe: `--text`, `--text-secondary`, `--text-faint`, `--text-muted`, `--border`, `--border-strong`, `--space-4/6/8/10/14`, `--text-table`, `--text-chip`, `--text-micro`, `--section-gap`).
- Narrow verification per task: `npm --prefix frontend test -- --include <spec> --watch=false`. **Never `cd` in Bash.** Stage files by name, never `git add -A`. Do not bump `VERSION.json`.

# Phase 4: the store

### Task V151-8: Models + `TradeDetailStore` computeds

**Model:** sonnet — typed narrowers over a loose wire shape across two files, with a fixed contract to match.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`TradeDetailFields`, :173-211; new types just above it)
- Modify: `frontend/src/app/stores/trade-detail.store.ts` (import line :14; new narrowers after `toSources`, ~:145; new computeds before `detailAbsent`, ~:357)
- Test: `frontend/src/app/stores/trade-detail.narrowing.spec.ts` (append one `describe` block)

**Interfaces:**
- Consumes: the wire keys V151-3 adds to `GET /api/v1/trades/<id>` `detail` (index § Wire contract). The store must also accept a response that lacks every one of them (a server from before V151-3, or a fixture), and must never throw on a wrong type.
- Produces (exact names; V151-9..V151-16 bind to them):
  - `models.ts`: `export type GateKey = 'rs' | 'regime' | 'earnings'`; `export interface GatePart { label: string; value: number | string | null; }`; `export interface GateRow { key: GateKey; label: string; value: number | string | null; threshold: number | null; margin: number | null; applies: boolean; parts: GatePart[]; note: string | null; }`; `export interface CalendarRow { date: string; kind: 'opex_monthly'; label: string; }`; `TradeDetailFields` gains `entry_context`, `risk_features`, `cohort_label`, `confidence_points`, `confidence_unevaluated`, `gates`, `sessions_since_created`, `expires_on`, `time_exit_on`, `calendar`, `hold_cap_bars`, `acceptance_level`.
  - Store computeds: `entryContext: Record<string, unknown>` (`{}` when absent), `riskFeatures: Record<string, unknown>` (`{}`), `confidencePoints: Record<string, number> | null` (null when absent, not a record, or empty after dropping non-numbers), `confidenceUnevaluated: string[]`, `gates: GateRow[]`, `calendar: CalendarRow[]`, `sessionsSinceCreated: number | null`, `expiresOn: string | null`, `timeExitOn: string | null`, `holdCapBars: number | null`, `acceptanceLevel: number | null`, `gapP90Pct: number | null` (from `entry_context.gap_p90_pct`, a percent figure), `gapFragile: boolean | null` (from `entry_context.gap_fragile`; null unless a real boolean).
  - `detailAbsent` is **unchanged**.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/stores/trade-detail.narrowing.spec.ts`, after the last `describe` block. The file already defines `FakeEventStream`, `ID`, `FULL_DETAIL`, `LEGACY_DETAIL` and `response(detail)`, and imports everything used below.

```ts
/* v151 — the Why panel's inputs.
 *
 * The keys are API-only (no stored record changes shape), and two of them are
 * v146's, which may not be on the server yet: every computed must answer the
 * same for "absent" as for "empty", and drop what it cannot read.
 */
const WHY_DETAIL = {
  ...FULL_DETAIL,
  entry_context: {
    regime2_state: 'BULL_QUIET', rs_pctile: 18, sector_pctile: 40, rs_combined: 22,
    htf_aligned: true, gap_p90_pct: 1.85, gap_fragile: true,
  },
  risk_features: { days_to_earnings: null, confluence_count: 3 },
  cohort_label: 'COHORT_TYPICAL',
  confidence_points: { 'Trend alignment': 12, Volume: 6, Regime: 7, Junk: 'x' },
  confidence_unevaluated: ['Regime', 42, ''],
  gates: [
    {
      key: 'rs', label: 'Relative strength', value: 22, threshold: 25, margin: 3,
      applies: true,
      parts: [
        { label: 'Ticker RS pctile', value: 18 },
        { label: 'Sector RS pctile', value: 40 },
        { value: 1 },
      ],
      note: null,
    },
    {
      key: 'regime', label: 'Regime', value: 'BULL_QUIET', threshold: null, margin: null,
      applies: false, parts: [], note: 'COHORT_TYPICAL',
    },
    { key: 'volume', label: 'Not a gate', value: 1, applies: true, parts: [], note: null },
    'garbage',
  ],
  sessions_since_created: 3,
  expires_on: '2026-08-08',
  time_exit_on: null,
  calendar: [
    { date: '2026-08-21', kind: 'opex_monthly', label: 'Monthly OPEX' },
    { date: '2026-08-14', kind: 'weekly' },
    { kind: 'opex_monthly' },
  ],
  hold_cap_bars: 10,
  acceptance_level: 101.25,
};

describe('TradeDetailStore — v151 Why panel inputs', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        TradeDetailStore,
      ],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const open = (detail: object) => {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(response(detail));
  };

  it('keeps only the numeric confidence points', () => {
    open(WHY_DETAIL);
    expect(store.confidencePoints()).toEqual({ 'Trend alignment': 12, Volume: 6, Regime: 7 });
  });

  it('is null when confidence_points is absent (a record from before v146)', () => {
    open(FULL_DETAIL);
    expect(store.confidencePoints()).toBeNull();
  });

  it('treats an all-junk points map as absent', () => {
    open({ ...WHY_DETAIL, confidence_points: { A: 'x' } });
    expect(store.confidencePoints()).toBeNull();
  });

  it('reads confidence_unevaluated as text, dropping blanks', () => {
    open(WHY_DETAIL);
    expect(store.confidenceUnevaluated()).toEqual(['Regime', '42']);
  });

  it('defaults confidence_unevaluated to an empty list', () => {
    open(FULL_DETAIL);
    expect(store.confidenceUnevaluated()).toEqual([]);
  });

  it('narrows gate rows and drops unknown keys and junk', () => {
    open(WHY_DETAIL);
    expect(store.gates()).toEqual([
      {
        key: 'rs', label: 'Relative strength', value: 22, threshold: 25, margin: 3,
        applies: true,
        parts: [
          { label: 'Ticker RS pctile', value: 18 },
          { label: 'Sector RS pctile', value: 40 },
        ],
        note: null,
      },
      {
        key: 'regime', label: 'Regime', value: 'BULL_QUIET', threshold: null, margin: null,
        applies: false, parts: [], note: 'COHORT_TYPICAL',
      },
    ]);
  });

  it('keeps only monthly OPEX calendar rows that carry a date', () => {
    open(WHY_DETAIL);
    expect(store.calendar()).toEqual([
      { date: '2026-08-21', kind: 'opex_monthly', label: 'Monthly OPEX' },
    ]);
  });

  it('reads the scalar timing and level fields', () => {
    open(WHY_DETAIL);
    expect(store.sessionsSinceCreated()).toBe(3);
    expect(store.expiresOn()).toBe('2026-08-08');
    expect(store.timeExitOn()).toBeNull();
    expect(store.holdCapBars()).toBe(10);
    expect(store.acceptanceLevel()).toBe(101.25);
  });

  it('reads gap risk out of entry_context', () => {
    open(WHY_DETAIL);
    expect(store.gapP90Pct()).toBe(1.85);
    expect(store.gapFragile()).toBe(true);
    expect(store.entryContext()['regime2_state']).toBe('BULL_QUIET');
    expect(store.riskFeatures()['confluence_count']).toBe(3);
  });

  it('does not read a string "true" as a fragile gap', () => {
    open({ ...WHY_DETAIL, entry_context: { gap_p90_pct: '1.8', gap_fragile: 'true' } });
    expect(store.gapP90Pct()).toBeNull();
    expect(store.gapFragile()).toBeNull();
  });

  it('answers every v151 field with its empty form on a legacy row', () => {
    open(LEGACY_DETAIL);
    expect(store.entryContext()).toEqual({});
    expect(store.riskFeatures()).toEqual({});
    expect(store.confidencePoints()).toBeNull();
    expect(store.confidenceUnevaluated()).toEqual([]);
    expect(store.gates()).toEqual([]);
    expect(store.calendar()).toEqual([]);
    expect(store.sessionsSinceCreated()).toBeNull();
    expect(store.expiresOn()).toBeNull();
    expect(store.timeExitOn()).toBeNull();
    expect(store.holdCapBars()).toBeNull();
    expect(store.acceptanceLevel()).toBeNull();
    expect(store.gapP90Pct()).toBeNull();
    expect(store.gapFragile()).toBeNull();
  });

  it('leaves detailAbsent unchanged by the new keys', () => {
    open({ ...LEGACY_DETAIL, gates: WHY_DETAIL.gates, calendar: WHY_DETAIL.calendar });
    expect(store.detailAbsent()).toBe(true);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/stores/trade-detail.narrowing.spec.ts --watch=false`
Expected: FAIL. The compile reports `Property 'confidencePoints' does not exist` (and the other new computeds).

- [ ] **Step 3: Add the wire types to `models.ts`**

In `frontend/src/app/api/models.ts`, insert directly above the doc comment of `export interface TradeDetailFields` (the `/** The heavy half of a trade, fetched only for the detail view.` block, ~:168):

```ts
/** v151 — one row of `detail.gates`, built server-side by
 *  `swingbot/core/presentation/why_view.py:gate_rows`. `threshold` is today's
 *  config, not the value in force at issuance; `margin` is signed (> 0 =
 *  cleared by this much). `applies` false = gate off, arm disabled or exempt;
 *  the row is still shown. */
export type GateKey = 'rs' | 'regime' | 'earnings';
export interface GatePart {
  label: string;
  value: number | string | null;
}
export interface GateRow {
  key: GateKey;
  label: string;
  value: number | string | null;
  threshold: number | null;
  margin: number | null;
  applies: boolean;
  parts: GatePart[];
  note: string | null;
}
/** v151 — one row of `detail.calendar` (`why_view.py:calendar_rows`). Only
 *  monthly OPEX ships; earnings and macro dates are out of scope. */
export interface CalendarRow {
  date: string;
  kind: 'opex_monthly';
  label: string;
}

```

Then, inside `TradeDetailFields`, replace its closing lines

```ts
  sizing_mode: string | null;
  account_balance_after: number | null;
}
```

with

```ts
  sizing_mode: string | null;
  account_balance_after: number | null;
  /* -- v151: the Why panel. API-only keys; both origins carry all of them. */
  /** Only the gate keys, `htf_aligned`, `gap_p90_pct` and `gap_fragile`. */
  entry_context: Record<string, unknown>;
  risk_features: Record<string, unknown>;
  cohort_label: string | null;
  /** v146's factor -> integer points. Null on a record written before v146. */
  confidence_points: Record<string, number> | null;
  /** v146's factors whose points were a neutral fallback. */
  confidence_unevaluated: string[];
  gates: GateRow[];
  sessions_since_created: number | null;
  /** ISO session date; PENDING plans only. */
  expires_on: string | null;
  /** ISO session date; once filled and only when `hold_cap_bars` is set. */
  time_exit_on: string | null;
  calendar: CalendarRow[];
  hold_cap_bars: number | null;
  acceptance_level: number | null;
}
```

No spec types a fixture as `TradeDetailFields` (`git grep -n "TradeDetailFields" -- frontend/src` finds only `models.ts` and comments), so making the keys required breaks no compile.

- [ ] **Step 4: Add the narrowers to the store**

In `frontend/src/app/stores/trade-detail.store.ts`, change the models import (:14) to:

```ts
import {
  AnalyticsStrategies,
  CalendarRow,
  GateKey,
  GatePart,
  GateRow,
  JournalEntry,
  TradeDetail,
} from '../api/models';
```

Insert after the end of `toSources` (before `interface TradeDetailSlice`):

```ts
/* -- v151: the Why panel's inputs ---------------------------------------
 *
 * Same rule as above: the server owns these shapes, so every narrower drops
 * what it cannot read. Two of the keys are v146's and may be absent on the
 * wire; "absent" and "empty" narrow to the same value.
 */

const GATE_KEYS: ReadonlySet<string> = new Set<GateKey>(['rs', 'regime', 'earnings']);

/** A gate value is a number (a percentile) or a word (a regime state).
 *  Numbers are tried first, because `asText` would stringify one. */
function asGateValue(value: unknown): number | string | null {
  return asNumber(value) ?? asText(value);
}

/** v146's factor -> points map. Non-numeric points are dropped; a map with
 *  nothing readable left is null, so the panel falls back to the text
 *  breakdown instead of rendering an empty points table. */
function toConfidencePoints(raw: unknown): Record<string, number> | null {
  if (!isRecord(raw)) return null;
  const out: Record<string, number> = {};
  for (const [factor, points] of Object.entries(raw)) {
    const value = asNumber(points);
    if (value !== null) out[factor] = value;
  }
  return Object.keys(out).length ? out : null;
}

function toTextList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    const value = asText(item);
    return value === null ? [] : [value];
  });
}

function toGateParts(raw: unknown): GatePart[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((part) => {
    if (!isRecord(part)) return [];
    const label = asText(part['label']);
    return label === null ? [] : [{ label, value: asGateValue(part['value']) }];
  });
}

/** A row with an unknown `key` is dropped rather than rendered: the panel
 *  only knows how to word the three gates `gate_rows` builds. */
function toGates(raw: unknown): GateRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((row) => {
    if (!isRecord(row)) return [];
    const key = asText(row['key']);
    const label = asText(row['label']);
    if (key === null || label === null || !GATE_KEYS.has(key)) return [];
    return [{
      key: key as GateKey,
      label,
      value: asGateValue(row['value']),
      threshold: asNumber(row['threshold']),
      margin: asNumber(row['margin']),
      applies: row['applies'] === true,
      parts: toGateParts(row['parts']),
      note: asText(row['note']),
    }];
  });
}

function toCalendarRows(raw: unknown): CalendarRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((row) => {
    if (!isRecord(row) || row['kind'] !== 'opex_monthly') return [];
    const date = asText(row['date']);
    if (date === null) return [];
    return [{ date, kind: 'opex_monthly' as const, label: asText(row['label']) ?? 'Monthly OPEX' }];
  });
}

function recordOrEmpty(raw: unknown): Record<string, unknown> {
  return isRecord(raw) ? raw : {};
}
```

- [ ] **Step 5: Add the computeds**

In the same file, inside the `withComputed(...)` object, insert immediately **before** the doc comment of `detailAbsent` (the `/**` line above `* True when this record predates the detail capture entirely.`, ~:357):

```ts
    /* -- v151: the Why panel ------------------------------------------- */

    /** The plan's frozen gate context (the server sends only the keys the
     *  panel reads). `{}` on a legacy row, never null, so a template can
     *  index it without a guard. */
    entryContext: computed<Record<string, unknown>>(() =>
      recordOrEmpty(data()?.detail?.entry_context),
    ),
    riskFeatures: computed<Record<string, unknown>>(() =>
      recordOrEmpty(data()?.detail?.risk_features),
    ),

    /** v146's numeric points per confidence factor, or null — the panel's
     *  signal to fall back to `confidenceFactors`' text rows. */
    confidencePoints: computed<Record<string, number> | null>(() =>
      toConfidencePoints(data()?.detail?.confidence_points),
    ),
    /** The factors whose points were a neutral fallback, not a reading. */
    confidenceUnevaluated: computed<string[]>(() =>
      toTextList(data()?.detail?.confidence_unevaluated),
    ),

    gates: computed<GateRow[]>(() => toGates(data()?.detail?.gates)),
    calendar: computed<CalendarRow[]>(() => toCalendarRows(data()?.detail?.calendar)),

    sessionsSinceCreated: computed(() => asNumber(data()?.detail?.sessions_since_created)),
    expiresOn: computed(() => asText(data()?.detail?.expires_on)),
    timeExitOn: computed(() => asText(data()?.detail?.time_exit_on)),
    holdCapBars: computed(() => asNumber(data()?.detail?.hold_cap_bars)),
    acceptanceLevel: computed(() => asNumber(data()?.detail?.acceptance_level)),

    /** Gap risk for the Sizing panel: the 90th-percentile overnight gap, as a
     *  percent of price, and whether the stop sits inside that noise
     *  (`swingbot/core/edge/context.py`). A non-boolean `gap_fragile` is
     *  null, never truthy. */
    gapP90Pct: computed(() =>
      asNumber(recordOrEmpty(data()?.detail?.entry_context)['gap_p90_pct']),
    ),
    gapFragile: computed<boolean | null>(() => {
      const value = recordOrEmpty(data()?.detail?.entry_context)['gap_fragile'];
      return typeof value === 'boolean' ? value : null;
    }),

```

`asNumber` and `asText` take `unknown`, so `undefined` from an absent key narrows to `null` with no `?? null`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/stores/trade-detail.narrowing.spec.ts --watch=false`
Expected: PASS (every test in the file, old and new).

Then the neighbouring specs that share the store:

Run: `npm --prefix frontend test -- --include src/app/stores/trade-detail.store.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --watch=false`
Expected: PASS, unchanged.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/stores/trade-detail.store.ts frontend/src/app/stores/trade-detail.narrowing.spec.ts
git commit -m "feat(ui): v151 detail models and store computeds for the Why panel (V151-8)"
```

# Phase 5: the Why components (Group A, parallel after V151-8)

V151-9..V151-12 each create their own two files and touch nothing else, so they run in parallel. None of them is mounted on a page until V151-15 / V151-16.

### Task V151-9: `sb-why-panel`

**Model:** sonnet — the largest new component: five sections, verbatim copy, a margin-tone rule and points/text fallback, all against a fixed input contract.

**Files:**
- Create: `frontend/src/app/workspaces/trades/why/why-panel.ts`
- Test: `frontend/src/app/workspaces/trades/why/why-panel.spec.ts`

**Interfaces:**
- Consumes (types only): `GateRow`, `CalendarRow` from `frontend/src/app/api/models.ts` (V151-8); `Confirmation`, `ConfidenceFactor`, `QualityFactor` from `frontend/src/app/stores/trade-detail.store.ts` (exist). UI: `Panel` (`ui/layout`), `Chip` (`ui/chip`, inputs `label` required, `tone`), `InlineMd` (`ui/inline-md`, input `text`), formatters `num`, `signed`, `text` (`ui/format`).
- Produces (V151-15 and V151-16 bind to these exact names):
  - `export class WhyPanel` (selector `sb-why-panel`).
  - `export type WhySection = 'levels' | 'confidence' | 'gates' | 'calendar' | 'explanation'`; `export const WHY_SECTIONS: readonly WhySection[]` (all five, in that order).
  - `export const GATE_CAVEAT = "Margins are measured against today's thresholds, not the ones in force when this plan was issued."`
  - `export function marginTone(status: string | null, barsToExpiry: number | null, sessionsSinceCreated: number | null): 'signed' | 'neutral' | 'indicative'`.
  - Inputs, all optional: `sections: readonly WhySection[]` (default `WHY_SECTIONS`), `status: string | null`, `barsToExpiry: number | null`, `sessionsSinceCreated: number | null`, `entry`, `trigger`, `stop`, `target1`, `target2`, `acceptanceLevel` (all `number | null`, default `null`), `stopLabel: string` (default `'Stop'`), `targetSources`, `stopSources`, `target2Sources` (`string[]`, default `[]`), `confirmedBy: Confirmation[]`, `confidencePoints: Record<string, number> | null`, `confidenceUnevaluated: string[]`, `confidenceFactors: ConfidenceFactor[]`, `qualityFactors: QualityFactor[]`, `gates: GateRow[]`, `calendar: CalendarRow[]` (lists default `[]`, points default `null`), `explanation: string | null`.

**Rules this task implements (spec § Why panel sections):**
- **Levels & methods** (`sb-panel`, heading `Levels & methods`): rows Entry (or `Trigger` when `entry` is null and `trigger` is set), `stopLabel`, Target 1, Target 2, each with its price; then `Acceptance level` when set. Beneath, one line per non-empty source list, labelled `Target confirmed by` / `Stop confirmed by` / `Target 2 confirmed by` (index decision 8, the existing `trade-detail.spec.ts` asserts them). Then a `Confirmed by` label and the `confirmedBy` strategies with their horizon. Empty lists hide their line.
- **Confidence**: when `confidencePoints` is a non-empty record, one row per factor: name, signed points, the `confidenceFactors` note sharing the key (none when missing), an `unevaluated` chip (tooltip `no data — neutral points awarded`) and muted points when the factor is in `confidenceUnevaluated`; a `Total` row sums **every** row, unevaluated included. Otherwise the existing text rows. Heading `Confidence breakdown` both ways; hidden only when both are empty. `Quality breakdown` (signed points) follows when non-empty.
- **Gate margins** (heading verbatim `Gate margins (vs today's thresholds)`): one row per gate, never hidden: label, value, threshold, signed margin, an `off` chip (tooltip `off in current config`) when `applies` is false, `parts` inline, `note` muted. An empty `gates` list renders `—`. The caveat `GATE_CAVEAT` is a plain paragraph beneath the rows, always rendered, no toggle.
- **Margin tone** (`marginTone`): `'neutral'` when `status` is not one of `PENDING` / `ACTIVE` / `PARTIAL` (CLOSED, CANCELLED, null, anything else), or when it is `PENDING` with `barsToExpiry === 0` (expired). Otherwise `'indicative'` when `sessionsSinceCreated` is null or `> 5`; else `'signed'`. Only `'signed'` colours a margin (`pos` for > 0, `neg` for < 0, and only on a row whose gate `applies`). `'indicative'` also shows one `indicative` chip at the top of the section. A null age counts as indicative because "created ≤ 5 sessions ago" cannot be shown.
- **Calendar in the holding window**: one row per `calendar` entry (label, ISO date as sent); `None in the window` when empty.
- **Why this trade**: the `explanation` through `sb-inline-md`, hidden when null (as today).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/workspaces/trades/why/why-panel.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { CalendarRow, GateRow } from '../../../api/models';
import { GATE_CAVEAT, WHY_SECTIONS, WhyPanel, marginTone } from './why-panel';

const GATES: GateRow[] = [
  {
    key: 'rs', label: 'Relative strength', value: 22, threshold: 25, margin: 3,
    applies: true,
    parts: [
      { label: 'Ticker RS pctile', value: 18 },
      { label: 'Sector RS pctile', value: 40 },
    ],
    note: null,
  },
  {
    key: 'regime', label: 'Regime', value: 'BULL_QUIET', threshold: null, margin: null,
    applies: false, parts: [], note: 'COHORT_TYPICAL',
  },
  {
    key: 'earnings', label: 'Days to earnings', value: null, threshold: null, margin: null,
    applies: false, parts: [], note: 'not recorded on this plan',
  },
];

const CALENDAR: CalendarRow[] = [
  { date: '2026-08-21', kind: 'opex_monthly', label: 'Monthly OPEX' },
];

const BASE: Record<string, unknown> = {
  status: 'ACTIVE',
  barsToExpiry: null,
  sessionsSinceCreated: 2,
  entry: 100,
  trigger: null,
  stop: 95,
  target1: 110,
  target2: 120,
  acceptanceLevel: 101.25,
  targetSources: ['Fib 1.618', 'Prior high'],
  stopSources: ['Swing low'],
  target2Sources: [],
  confirmedBy: [{ strategy: 'VWAP', horizon: '2w' }],
  confidencePoints: null,
  confidenceUnevaluated: [],
  confidenceFactors: [{ factor: 'Trend alignment', note: '+12 — above the 200-day' }],
  qualityFactors: [{ label: 'Badge', points: 15 }, { label: 'R:R', points: -5 }],
  gates: GATES,
  calendar: CALENDAR,
  explanation: 'Price reclaimed the 50-day after a three-week base.',
};

function render(overrides: Record<string, unknown> = {}): HTMLElement {
  const fixture = TestBed.createComponent(WhyPanel);
  for (const [key, value] of Object.entries({ ...BASE, ...overrides })) {
    fixture.componentRef.setInput(key, value);
  }
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const textOf = (el: Element | null) => el?.textContent ?? '';
const rsMargin = (el: HTMLElement) =>
  el.querySelector<HTMLElement>('[data-gate="rs"] .margin')!;

describe('marginTone', () => {
  it('colours a fresh open plan', () => {
    expect(marginTone('ACTIVE', null, 0)).toBe('signed');
    expect(marginTone('PARTIAL', null, 5)).toBe('signed');
    expect(marginTone('PENDING', 3, 1)).toBe('signed');
  });

  it('goes neutral once the plan is over', () => {
    expect(marginTone('CLOSED', null, 1)).toBe('neutral');
    expect(marginTone('CANCELLED', null, 1)).toBe('neutral');
    expect(marginTone('PENDING', 0, 1)).toBe('neutral');
    expect(marginTone(null, null, 1)).toBe('neutral');
  });

  it('is indicative past five sessions, or when the age is unknown', () => {
    expect(marginTone('ACTIVE', null, 6)).toBe('indicative');
    expect(marginTone('ACTIVE', null, null)).toBe('indicative');
  });

  it('lets "over" win over "old"', () => {
    expect(marginTone('CLOSED', null, 40)).toBe('neutral');
  });
});

describe('WhyPanel (v151)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders all five sections by default, in order', () => {
    expect(WHY_SECTIONS).toEqual(['levels', 'confidence', 'gates', 'calendar', 'explanation']);
    const text = textOf(render());
    const order = [
      'Levels & methods', 'Confidence breakdown', "Gate margins (vs today's thresholds)",
      'Calendar in the holding window', 'Why this trade',
    ].map((heading) => text.indexOf(heading));
    expect(order.every((at) => at >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it('lists each level with the methods that confirmed it', () => {
    const text = textOf(render());
    expect(text).toContain('Entry');
    expect(text).toContain('Target confirmed by');
    expect(text).toContain('Fib 1.618, Prior high');
    expect(text).toContain('Stop confirmed by');
    expect(text).toContain('Swing low');
    expect(text).not.toContain('Target 2 confirmed by');
    expect(text).toContain('Confirmed by');
    expect(text).toContain('VWAP');
    expect(text).toContain('(2w)');
    expect(text).toContain('Acceptance level');
    expect(text).toContain('101.25');
  });

  it('shows the trigger in place of the entry on a pending plan', () => {
    const text = textOf(render({ entry: null, trigger: 101.5, status: 'PENDING' }));
    expect(text).toContain('Trigger');
    expect(text).toContain('101.50');
  });

  it('hides the source lines and confirmations when there are none', () => {
    const text = textOf(render({ targetSources: [], stopSources: [], confirmedBy: [] }));
    expect(text).not.toContain('confirmed by');
    expect(text).not.toContain('Confirmed by');
  });

  it('renders v146 points per factor with the matching note and a total', () => {
    const el = render({ confidencePoints: { 'Trend alignment': 12, Volume: 6 } });
    const rows = [...el.querySelectorAll('.points-row')].map((row) => textOf(row));
    expect(rows[0]).toContain('Trend alignment');
    expect(rows[0]).toContain('+12');
    expect(rows[0]).toContain('above the 200-day');
    expect(rows[1]).toContain('Volume');
    expect(rows[1]).toContain('+6');
    expect(textOf(el.querySelector('.points-total'))).toContain('+18');
    expect(el.querySelector('sb-chip[title="no data — neutral points awarded"]')).toBeNull();
  });

  it('marks an unevaluated factor, mutes its points and still totals it', () => {
    const el = render({
      confidencePoints: { 'Trend alignment': 12, Regime: 7 },
      confidenceUnevaluated: ['Regime'],
    });
    const regime = [...el.querySelectorAll('.points-row')].find((row) =>
      textOf(row).includes('Regime'),
    )!;
    expect(regime.querySelector('sb-chip[title="no data — neutral points awarded"]')).not.toBeNull();
    expect(textOf(regime)).toContain('unevaluated');
    expect(regime.querySelector('.points-value')!.classList).toContain('muted');
    expect(textOf(el.querySelector('.points-total'))).toContain('+19');
  });

  it('falls back to the text breakdown when there are no points (pre-v146)', () => {
    const el = render();
    expect(el.querySelectorAll('.points-row').length).toBe(0);
    expect(textOf(el)).toContain('+12 — above the 200-day');
    expect(textOf(el)).not.toContain('unevaluated');
  });

  it('keeps the quality breakdown, signed', () => {
    const text = textOf(render());
    expect(text).toContain('Quality breakdown');
    expect(text).toContain('+15');
    expect(text).toContain('-5');
  });

  it('colours margins on a fresh open plan', () => {
    expect(rsMargin(render()).classList).toContain('pos');
    const failing = render({ gates: [{ ...GATES[0], margin: -4 }] });
    expect(rsMargin(failing).classList).toContain('neg');
  });

  for (const [label, overrides] of [
    ['CLOSED', { status: 'CLOSED' }],
    ['CANCELLED', { status: 'CANCELLED' }],
    ['an expired PENDING', { status: 'PENDING', barsToExpiry: 0 }],
    ['a plan older than five sessions', { sessionsSinceCreated: 9 }],
  ] as const) {
    it(`keeps margins neutral on ${label}`, () => {
      const margin = rsMargin(render(overrides));
      expect(margin.classList).not.toContain('pos');
      expect(margin.classList).not.toContain('neg');
      expect(textOf(margin)).toContain('+3.0');
    });
  }

  it('flags an old plan as indicative, and only an old one', () => {
    expect(textOf(render({ sessionsSinceCreated: 9 }))).toContain('indicative');
    expect(textOf(render())).not.toContain('indicative');
  });

  it('shows every gate row, with an "off" chip where the gate does not apply', () => {
    const el = render();
    expect(el.querySelectorAll('.gate-row').length).toBe(3);
    const regime = el.querySelector('[data-gate="regime"]')!;
    expect(regime.querySelector('sb-chip[title="off in current config"]')).not.toBeNull();
    expect(textOf(regime)).toContain('COHORT_TYPICAL');
    const earnings = el.querySelector('[data-gate="earnings"]')!;
    expect(textOf(earnings)).toContain('—');
    expect(textOf(earnings)).toContain('not recorded on this plan');
    expect(el.querySelector('[data-gate="rs"] sb-chip')).toBeNull();
  });

  it('renders RS parts inline', () => {
    const rs = textOf(render().querySelector('[data-gate="rs"]'));
    expect(rs).toContain('Ticker RS pctile 18.0');
    expect(rs).toContain('Sector RS pctile 40.0');
    expect(rs).toContain('22.0');
    expect(rs).toContain('25.0');
  });

  it('always shows the caveat, with nothing that could hide it', () => {
    for (const gates of [GATES, []]) {
      const el = render({ gates });
      expect(textOf(el.querySelector('.caveat')).trim()).toBe(GATE_CAVEAT);
      expect(el.querySelector('details, button, sb-button')).toBeNull();
    }
  });

  it('renders an empty gate list as a measured dash, not a hidden section', () => {
    const el = render({ gates: [] });
    expect(textOf(el)).toContain("Gate margins (vs today's thresholds)");
    expect(textOf(el.querySelector('.gates-empty')).trim()).toBe('—');
  });

  it('lists the calendar rows, or says the window is empty', () => {
    expect(textOf(render())).toContain('Monthly OPEX');
    expect(textOf(render())).toContain('2026-08-21');
    expect(textOf(render({ calendar: [] }))).toContain('None in the window');
  });

  it('renders the explanation, and hides the section when there is none', () => {
    expect(textOf(render())).toContain('Price reclaimed the 50-day');
    expect(textOf(render({ explanation: null }))).not.toContain('Why this trade');
  });

  it('renders only the sections asked for', () => {
    const text = textOf(render({ sections: ['gates', 'calendar'] }));
    expect(text).toContain("Gate margins (vs today's thresholds)");
    expect(text).toContain('Calendar in the holding window');
    expect(text).not.toContain('Levels & methods');
    expect(text).not.toContain('Confidence breakdown');
    expect(text).not.toContain('Why this trade');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/why-panel.spec.ts --watch=false`
Expected: FAIL, `Cannot find module './why-panel'`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/trades/why/why-panel.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import type { CalendarRow, GateRow } from '../../../api/models';
import type {
  ConfidenceFactor,
  Confirmation,
  QualityFactor,
} from '../../../stores/trade-detail.store';
import { Chip } from '../../../ui/chip';
import { num, signed, text } from '../../../ui/format';
import { InlineMd } from '../../../ui/inline-md';
import { Panel } from '../../../ui/layout';

/** The five sections, in render order (spec v151 § Why panel sections). */
export type WhySection = 'levels' | 'confidence' | 'gates' | 'calendar' | 'explanation';
export const WHY_SECTIONS: readonly WhySection[] = [
  'levels', 'confidence', 'gates', 'calendar', 'explanation',
];

/** Verbatim, and never collapsible: the thresholds are today's config, not
 *  the ones frozen at issuance (they are not frozen on the plan at all). */
export const GATE_CAVEAT =
  "Margins are measured against today's thresholds, not the ones in force when this plan was issued.";

const GATE_HEADING = "Gate margins (vs today's thresholds)";
const OFF_TOOLTIP = 'off in current config';
const UNEVALUATED_TOOLTIP = 'no data — neutral points awarded';
const INDICATIVE_TOOLTIP =
  'Created more than 5 sessions ago (or age unknown): the threshold may have moved since issuance.';

const OPEN_STATUSES: ReadonlySet<string> = new Set(['PENDING', 'ACTIVE', 'PARTIAL']);
const FRESH_SESSIONS = 5;

/**
 * How to colour a gate margin.
 *
 * Today's threshold says nothing about a plan that is over, so CLOSED,
 * CANCELLED and an expired PENDING are neutral. An open plan older than five
 * sessions is "indicative": the threshold may have moved since it was issued.
 * An unknown age (outside the session calendar) cannot be shown to be fresh,
 * so it is indicative too. "Over" wins over "old".
 */
export function marginTone(
  status: string | null,
  barsToExpiry: number | null,
  sessionsSinceCreated: number | null,
): 'signed' | 'neutral' | 'indicative' {
  if (status === null || !OPEN_STATUSES.has(status)) return 'neutral';
  if (status === 'PENDING' && barsToExpiry === 0) return 'neutral';
  if (sessionsSinceCreated === null || sessionsSinceCreated > FRESH_SESSIONS) return 'indicative';
  return 'signed';
}

interface LevelRow {
  label: string;
  price: number | null;
  tone: 'pos' | 'neg' | '';
  sourcesLabel: string | null;
  sources: string[];
}

interface PointsRow {
  factor: string;
  points: number;
  note: string | null;
  unevaluated: boolean;
}

interface GateView {
  key: string;
  label: string;
  value: string;
  threshold: string;
  margin: string;
  marginClass: 'pos' | 'neg' | '';
  off: boolean;
  parts: string;
  note: string | null;
}

function gateValueText(value: number | string | null): string {
  return typeof value === 'number' ? num(value, 1) : text(value);
}

function marginClass(gate: GateRow, tone: string): 'pos' | 'neg' | '' {
  if (tone !== 'signed' || !gate.applies || gate.margin === null || gate.margin === 0) return '';
  return gate.margin > 0 ? 'pos' : 'neg';
}

function toGateView(gate: GateRow, tone: string): GateView {
  return {
    key: gate.key,
    label: gate.label,
    value: gateValueText(gate.value),
    threshold: num(gate.threshold, 1),
    margin: signed(gate.margin, 1),
    marginClass: marginClass(gate, tone),
    off: !gate.applies,
    parts: gate.parts.map((part) => `${part.label} ${gateValueText(part.value)}`).join(' · '),
    note: gate.note,
  };
}

/** Points are integers contributing to a total. Same sign rule as the trade
 *  page's quality breakdown, so the two read alike. */
function signedPoints(points: number): string {
  return `${points > 0 ? '+' : ''}${points}`;
}

/**
 * The Why panel (spec v151): every stored reason behind one plan, in one
 * place. Shared by the trade page (`trades/:id`) and the plan page
 * (`plans/:id`). Plain inputs only — the page passes its store's signals in,
 * so this component never knows which page it is on.
 */
@Component({
  selector: 'sb-why-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip, InlineMd, Panel],
  template: `
    @if (shown().has('levels')) {
      <sb-panel [heading]="'Levels & methods'">
        <dl class="factors">
          @for (row of levelRows(); track row.label) {
            <div>
              <dt>{{ row.label }}</dt>
              <dd class="num" [class.pos]="row.tone === 'pos'" [class.neg]="row.tone === 'neg'">
                {{ fmt(row.price) }}
              </dd>
            </div>
          }
          @if (acceptanceLevel() !== null) {
            <div>
              <dt>Acceptance level</dt>
              <dd class="num">{{ fmt(acceptanceLevel()) }}</dd>
            </div>
          }
        </dl>
        @if (hasSources()) {
          <div class="sources">
            @for (row of levelRows(); track row.label) {
              @if (row.sourcesLabel && row.sources.length) {
                <p><span class="src-label">{{ row.sourcesLabel }}</span>
                  {{ row.sources.join(', ') }}</p>
              }
            }
          </div>
        }
        @if (confirmedBy().length) {
          <div class="sources">
            <span class="src-label">Confirmed by</span>
            <ul class="confirmations">
              @for (c of confirmedBy(); track c.strategy + (c.horizon ?? '')) {
                <li>
                  {{ c.strategy }}
                  @if (c.horizon) {
                    <span class="muted muted-gap">({{ c.horizon }})</span>
                  }
                </li>
              }
            </ul>
          </div>
        }
      </sb-panel>
    }

    @if (shown().has('confidence')) {
      @if (pointsRows(); as rows) {
        <sb-panel heading="Confidence breakdown">
          <dl class="factors">
            @for (row of rows; track row.factor) {
              <div class="points-row">
                <dt>
                  {{ row.factor }}
                  @if (row.unevaluated) {
                    <sb-chip label="unevaluated" tone="muted" [title]="unevaluatedTooltip" />
                  }
                </dt>
                <dd>
                  @if (row.note) {
                    <span class="point-note">{{ row.note }}</span>
                  }
                  <span class="num points-value" [class.muted]="row.unevaluated">
                    {{ signedPoints(row.points) }}
                  </span>
                </dd>
              </div>
            }
            <div class="points-total">
              <dt>Total</dt>
              <dd class="num">{{ signedPoints(pointsTotal()) }}</dd>
            </div>
          </dl>
        </sb-panel>
      } @else if (confidenceFactors().length) {
        <sb-panel heading="Confidence breakdown">
          <dl class="factors">
            @for (f of confidenceFactors(); track f.factor) {
              <div><dt>{{ f.factor }}</dt><dd>{{ f.note }}</dd></div>
            }
          </dl>
        </sb-panel>
      }
      @if (qualityFactors().length) {
        <sb-panel heading="Quality breakdown">
          <dl class="factors">
            @for (f of qualityFactors(); track f.label) {
              <div>
                <dt>{{ f.label }}</dt>
                <dd class="num">{{ signedPoints(f.points) }}</dd>
              </div>
            }
          </dl>
        </sb-panel>
      }
    }

    @if (shown().has('gates')) {
      <sb-panel [heading]="gateHeading">
        @if (tone() === 'indicative') {
          <p class="gate-flag">
            <sb-chip label="indicative" tone="warn" [title]="indicativeTooltip" />
          </p>
        }
        @if (gateViews().length) {
          <dl class="factors">
            @for (g of gateViews(); track g.key) {
              <div class="gate-row" [attr.data-gate]="g.key">
                <dt>
                  {{ g.label }}
                  @if (g.off) {
                    <sb-chip label="off" tone="muted" [title]="offTooltip" />
                  }
                  @if (g.parts) {
                    <span class="gate-sub">{{ g.parts }}</span>
                  }
                  @if (g.note) {
                    <span class="gate-sub muted">{{ g.note }}</span>
                  }
                </dt>
                <dd class="gate-figures">
                  <span class="num" title="value">{{ g.value }}</span>
                  <span class="muted">vs</span>
                  <span class="num" title="threshold (current config)">{{ g.threshold }}</span>
                  <span
                    class="num margin"
                    title="margin"
                    [class.pos]="g.marginClass === 'pos'"
                    [class.neg]="g.marginClass === 'neg'"
                  >{{ g.margin }}</span>
                </dd>
              </div>
            }
          </dl>
        } @else {
          <p class="gates-empty">—</p>
        }
        <p class="caveat">{{ caveat }}</p>
      </sb-panel>
    }

    @if (shown().has('calendar')) {
      <sb-panel heading="Calendar in the holding window">
        @if (calendar().length) {
          <dl class="factors">
            @for (row of calendar(); track row.date) {
              <div><dt>{{ row.label }}</dt><dd class="num">{{ row.date }}</dd></div>
            }
          </dl>
        } @else {
          <p class="empty-line">None in the window</p>
        }
      </sb-panel>
    }

    @if (shown().has('explanation')) {
      @if (explanation(); as why) {
        <sb-panel heading="Why this trade">
          <p class="prose"><sb-inline-md [text]="why" /></p>
        </sb-panel>
      }
    }
  `,
  styles: `
    :host { display: grid; gap: var(--section-gap); align-content: start; }
    dl { display: grid; gap: var(--space-6); }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }
    .factors > div { align-items: baseline; gap: var(--space-14); }
    .factors dd { text-align: right; }
    .sources {
      margin-top: var(--space-10);
      padding-top: var(--space-10);
      border-top: 1px solid var(--border);
    }
    .sources p { color: var(--text); font-size: var(--text-chip); line-height: 1.5; }
    .src-label {
      display: block;
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .confirmations { display: grid; gap: var(--space-6); list-style: none; }
    .confirmations li { color: var(--text); font-size: var(--text-table); }
    .muted-gap { margin-left: var(--space-6); }
    .point-note { margin-right: var(--space-8); color: var(--text-secondary); }
    .points-total { padding-top: var(--space-6); border-top: 1px solid var(--border); }
    .gate-sub { display: block; font-size: var(--text-chip); }
    .gate-figures { display: flex; gap: var(--space-6); align-items: baseline; }
    .gate-flag { margin-bottom: var(--space-8); }
    .caveat, .empty-line, .gates-empty {
      margin-top: var(--space-8);
      color: var(--text-faint);
      font-size: var(--text-chip);
      line-height: 1.5;
    }
    .prose { max-width: 68ch; color: var(--text); font-size: var(--text-table); line-height: 1.6; }
  `,
})
export class WhyPanel {
  readonly sections = input<readonly WhySection[]>(WHY_SECTIONS);
  readonly status = input<string | null>(null);
  readonly barsToExpiry = input<number | null>(null);
  readonly sessionsSinceCreated = input<number | null>(null);

  readonly entry = input<number | null>(null);
  readonly trigger = input<number | null>(null);
  readonly stop = input<number | null>(null);
  readonly stopLabel = input<string>('Stop');
  readonly target1 = input<number | null>(null);
  readonly target2 = input<number | null>(null);
  readonly acceptanceLevel = input<number | null>(null);
  readonly targetSources = input<string[]>([]);
  readonly stopSources = input<string[]>([]);
  readonly target2Sources = input<string[]>([]);
  readonly confirmedBy = input<Confirmation[]>([]);

  readonly confidencePoints = input<Record<string, number> | null>(null);
  readonly confidenceUnevaluated = input<string[]>([]);
  readonly confidenceFactors = input<ConfidenceFactor[]>([]);
  readonly qualityFactors = input<QualityFactor[]>([]);

  readonly gates = input<GateRow[]>([]);
  readonly calendar = input<CalendarRow[]>([]);
  readonly explanation = input<string | null>(null);

  protected readonly caveat = GATE_CAVEAT;
  protected readonly gateHeading = GATE_HEADING;
  protected readonly offTooltip = OFF_TOOLTIP;
  protected readonly unevaluatedTooltip = UNEVALUATED_TOOLTIP;
  protected readonly indicativeTooltip = INDICATIVE_TOOLTIP;
  protected readonly fmt = num;
  protected readonly signedPoints = signedPoints;

  protected readonly shown = computed(() => new Set<WhySection>(this.sections()));

  /** Entry once filled; the trigger while a stop-entry plan still waits. */
  protected readonly levelRows = computed<LevelRow[]>(() => {
    const waiting = this.entry() === null && this.trigger() !== null;
    return [
      {
        label: waiting ? 'Trigger' : 'Entry',
        price: waiting ? this.trigger() : this.entry(),
        tone: '', sourcesLabel: null, sources: [],
      },
      {
        label: this.stopLabel(), price: this.stop(), tone: 'neg',
        sourcesLabel: 'Stop confirmed by', sources: this.stopSources(),
      },
      {
        label: 'Target 1', price: this.target1(), tone: 'pos',
        sourcesLabel: 'Target confirmed by', sources: this.targetSources(),
      },
      {
        label: 'Target 2', price: this.target2(), tone: 'pos',
        sourcesLabel: 'Target 2 confirmed by', sources: this.target2Sources(),
      },
    ];
  });

  protected readonly hasSources = computed(() =>
    this.levelRows().some((row) => row.sources.length > 0),
  );

  /** Null when there are no v146 points — the template's cue for the text
   *  breakdown. An unevaluated factor stays in the list (and the total): the
   *  total must reconcile with the quality score. */
  protected readonly pointsRows = computed<PointsRow[] | null>(() => {
    const points = this.confidencePoints();
    if (points === null || Object.keys(points).length === 0) return null;
    const notes = new Map(this.confidenceFactors().map((f) => [f.factor, f.note]));
    const unevaluated = new Set(this.confidenceUnevaluated());
    return Object.entries(points).map(([factor, value]) => ({
      factor,
      points: value,
      note: notes.get(factor) ?? null,
      unevaluated: unevaluated.has(factor),
    }));
  });

  protected readonly pointsTotal = computed(() =>
    (this.pointsRows() ?? []).reduce((sum, row) => sum + row.points, 0),
  );

  protected readonly tone = computed(() =>
    marginTone(this.status(), this.barsToExpiry(), this.sessionsSinceCreated()),
  );

  protected readonly gateViews = computed<GateView[]>(() => {
    const tone = this.tone();
    return this.gates().map((gate) => toGateView(gate, tone));
  });
}
```

Notes for the implementer:
- `[heading]="'Levels & methods'"` is a binding on purpose: a bare `&` inside a static attribute is an HTML entity start.
- The quality breakdown keeps the trade page's ASCII hyphen-minus sign (`-5`), so the existing `trade-detail.spec.ts` assertions (`+15`) hold when V151-15 swaps the panel in. Gate margins use `signed()` from `ui/format` (U+2212 minus), as every other signed figure does.
- `.muted` and `.pos` / `.neg` are the global classes from `styles.css`; do not define them here (`ui/primitives.spec.ts`).
- Never give these `sb-panel`s a `digest`: a panel with a digest becomes collapsible (`ui/layout.ts`), and the gate caveat must never fold away. The caveat test asserts there is no `button` in the component.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/why-panel.spec.ts --watch=false`
Expected: PASS.

Then the call-site gates, which scan the new file:

Run: `npm --prefix frontend test -- --include src/app/ui/primitives.spec.ts --include src/app/ui/spacing.spec.ts --watch=false`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/why-panel.ts frontend/src/app/workspaces/trades/why/why-panel.spec.ts
git commit -m "feat(ui): v151 shared Why panel component (V151-9)"
```

### Task V151-10: `sb-levels-block` (order-ready)

**Model:** sonnet — extraction of the Levels panel plus a direction-aware wording table; small but the trade page's existing assertions depend on it.

**Files:**
- Create: `frontend/src/app/workspaces/trades/why/levels-block.ts`
- Test: `frontend/src/app/workspaces/trades/why/levels-block.spec.ts`

**Interfaces:**
- Consumes: `Panel` (`ui/layout`), `num`, `share`, `text` (`ui/format`). Extracted from `trade-detail.ts:161-208` (the Levels `<dl>`; its `.sources` block is **not** carried over, the Why panel owns sources now).
- Produces: `export class LevelsBlock` (selector `sb-levels-block`); `export function entryTypeWord(entryType: string | null, direction: string | null): string`; `export const PAPER_LINE = 'Paper plan — this page places no orders.'`. Inputs, all defaulting to `null` except `stopLabel` (default `'Stop'`): `direction: string | null`, `entryType: string | null`, `trigger`, `entry`, `stop`, `target1`, `target2`, `riskReward`, `acceptanceLevel`, `tp1Pct`, `breakevenTriggerPct` (all `number | null`), `stopLabel: string`.

**Rules (spec § Levels block):** one `sb-panel` headed `Levels` (the trade page's heading, kept). Rows in this order: `Order` (the entry type in words), `Trigger` (only when set, as today), `Entry`, `stopLabel` (`neg`), `Target 1` and `Target 2` (`pos`), `R:R`, then `Acceptance level`, `TP1 closes` and `Break-even at … of TP1`, each only when set. Wording: `stop_entry` → `Buy stop` / `Sell stop`, `limit` → `Buy limit` / `Sell limit` (by direction, `bullish` / `bearish`), `market` → `At market`; with no known direction, `Stop entry` / `Limit entry`; null → `—`; any other string is shown as sent. Under the list, always, the muted line `PAPER_LINE`. Nothing here is a control: no button, link or input.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/workspaces/trades/why/levels-block.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LevelsBlock, PAPER_LINE, entryTypeWord } from './levels-block';

const BASE: Record<string, unknown> = {
  direction: 'bullish',
  entryType: 'stop_entry',
  trigger: 101.5,
  entry: null,
  stop: 95,
  target1: 110,
  target2: 120,
  riskReward: 2.4,
};

function render(overrides: Record<string, unknown> = {}): HTMLElement {
  const fixture = TestBed.createComponent(LevelsBlock);
  for (const [key, value] of Object.entries({ ...BASE, ...overrides })) {
    fixture.componentRef.setInput(key, value);
  }
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const labels = (el: HTMLElement) =>
  [...el.querySelectorAll('dt')].map((dt) => (dt.textContent ?? '').trim());

describe('entryTypeWord', () => {
  for (const [type, direction, word] of [
    ['stop_entry', 'bullish', 'Buy stop'],
    ['stop_entry', 'bearish', 'Sell stop'],
    ['limit', 'bullish', 'Buy limit'],
    ['limit', 'bearish', 'Sell limit'],
    ['market', 'bullish', 'At market'],
    ['market', 'bearish', 'At market'],
    ['stop_entry', null, 'Stop entry'],
    ['limit', null, 'Limit entry'],
    [null, 'bullish', '—'],
    ['stop', 'bullish', 'stop'],
  ] as const) {
    it(`words ${type} / ${direction} as "${word}"`, () => {
      expect(entryTypeWord(type, direction)).toBe(word);
    });
  }
});

describe('LevelsBlock (v151)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('reads like an order ticket: type, trigger, entry, stop, targets, R:R', () => {
    expect(labels(render())).toEqual([
      'Order', 'Trigger', 'Entry', 'Stop', 'Target 1', 'Target 2', 'R:R',
    ]);
    const text = render().textContent ?? '';
    expect(text).toContain('Buy stop');
    expect(text).toContain('101.50');
    expect(text).toContain('2.40');
  });

  it('words a short limit order', () => {
    expect(render({ direction: 'bearish', entryType: 'limit' }).textContent).toContain('Sell limit');
  });

  it('drops the trigger row once there is none', () => {
    expect(labels(render({ trigger: null, entry: 100 }))).not.toContain('Trigger');
  });

  it('colours the stop and the targets', () => {
    const el = render();
    const dds = [...el.querySelectorAll('dd')];
    expect(dds[labels(el).indexOf('Stop')].classList).toContain('neg');
    expect(dds[labels(el).indexOf('Target 1')].classList).toContain('pos');
  });

  it('uses the caller\'s stop label', () => {
    expect(labels(render({ stopLabel: 'Trailing stop' }))).toContain('Trailing stop');
  });

  it('adds acceptance, TP1 share and break-even only when set', () => {
    expect(labels(render())).not.toContain('TP1 closes');
    const el = render({ acceptanceLevel: 101.25, tp1Pct: 50, breakevenTriggerPct: 60 });
    expect(labels(el)).toEqual(expect.arrayContaining(['Acceptance level', 'TP1 closes', 'Break-even at']));
    expect(el.textContent).toContain('50%');
    expect(el.textContent).toContain('60% of TP1');
  });

  it('always says it places no orders, and offers no control', () => {
    for (const overrides of [{}, { entryType: null, direction: null }]) {
      const el = render(overrides);
      expect(el.querySelector('.paper-line')!.textContent!.trim()).toBe(PAPER_LINE);
      expect(el.querySelector('.paper-line')!.classList).toContain('muted');
      expect(el.querySelector('button, a, input, sb-button')).toBeNull();
    }
    expect(PAPER_LINE).toBe('Paper plan — this page places no orders.');
  });

  it('keeps the trade page heading', () => {
    expect(render().textContent).toContain('Levels');
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/levels-block.spec.ts --watch=false`
Expected: FAIL, `Cannot find module './levels-block'`.

- [ ] **Step 3: Write the component**

Create `frontend/src/app/workspaces/trades/why/levels-block.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { num, share, text } from '../../../ui/format';
import { Panel } from '../../../ui/layout';

/** Verbatim. The bot is paper-only: this page places, edits and cancels
 *  nothing, and says so where the prices are. */
export const PAPER_LINE = 'Paper plan — this page places no orders.';

/** `plan_types.py:30` entry types, worded the way an order ticket reads. */
const ENTRY_WORDS: Record<string, { bullish: string; bearish: string; unknown: string }> = {
  stop_entry: { bullish: 'Buy stop', bearish: 'Sell stop', unknown: 'Stop entry' },
  limit: { bullish: 'Buy limit', bearish: 'Sell limit', unknown: 'Limit entry' },
  market: { bullish: 'At market', bearish: 'At market', unknown: 'At market' },
};

export function entryTypeWord(entryType: string | null, direction: string | null): string {
  if (entryType === null) return text(null);
  const words = ENTRY_WORDS[entryType];
  if (!words) return entryType;
  if (direction === 'bullish' || direction === 'bearish') return words[direction];
  return words.unknown;
}

/**
 * The plan's levels, order-ready (spec v151 § Levels block). Extracted from
 * the trade page's Levels panel; the per-level sources it used to carry now
 * render once, in the Why panel. Read-only by construction: no control here.
 */
@Component({
  selector: 'sb-levels-block',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Levels">
      <dl>
        <div>
          <dt>Order</dt>
          <dd>{{ orderWord() }}</dd>
        </div>
        <!-- The only actionable price on a PENDING plan: entry stays null
             until it fills. Hidden once there is none. -->
        @if (trigger() !== null) {
          <div>
            <dt>Trigger</dt>
            <dd class="num">{{ fmt(trigger()) }}</dd>
          </div>
        }
        <div>
          <dt>Entry</dt>
          <dd class="num">{{ fmt(entry()) }}</dd>
        </div>
        <div>
          <dt>{{ stopLabel() }}</dt>
          <dd class="num neg">{{ fmt(stop()) }}</dd>
        </div>
        <div>
          <dt>Target 1</dt>
          <dd class="num pos">{{ fmt(target1()) }}</dd>
        </div>
        <div>
          <dt>Target 2</dt>
          <dd class="num pos">{{ fmt(target2()) }}</dd>
        </div>
        <div>
          <dt>R:R</dt>
          <dd class="num">{{ fmt(riskReward()) }}</dd>
        </div>
        @if (acceptanceLevel() !== null) {
          <div>
            <dt>Acceptance level</dt>
            <dd class="num">{{ fmt(acceptanceLevel()) }}</dd>
          </div>
        }
        @if (tp1Pct() !== null) {
          <div>
            <dt>TP1 closes</dt>
            <dd class="num">{{ fmtShare(tp1Pct()) }}</dd>
          </div>
        }
        @if (breakevenTriggerPct() !== null) {
          <div>
            <dt>Break-even at</dt>
            <dd class="num">{{ fmtShare(breakevenTriggerPct()) }} of TP1</dd>
          </div>
        }
      </dl>
      <p class="paper-line muted">{{ paperLine }}</p>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    dl { display: grid; gap: var(--space-6); }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }
    .paper-line { margin-top: var(--space-10); font-size: var(--text-chip); }
  `,
})
export class LevelsBlock {
  readonly direction = input<string | null>(null);
  readonly entryType = input<string | null>(null);
  readonly trigger = input<number | null>(null);
  readonly entry = input<number | null>(null);
  readonly stop = input<number | null>(null);
  readonly stopLabel = input<string>('Stop');
  readonly target1 = input<number | null>(null);
  readonly target2 = input<number | null>(null);
  readonly riskReward = input<number | null>(null);
  readonly acceptanceLevel = input<number | null>(null);
  readonly tp1Pct = input<number | null>(null);
  readonly breakevenTriggerPct = input<number | null>(null);

  protected readonly paperLine = PAPER_LINE;
  protected readonly fmt = num;
  protected readonly fmtShare = share;
  protected readonly orderWord = computed(() =>
    entryTypeWord(this.entryType(), this.direction()),
  );
}
```

`.pos` / `.neg` / `.muted` / `.num` are the global classes from `styles.css`; never define them here. The `dl` / `dt` / `dd` rules are copied from `trade-detail.ts` unchanged, so the block renders exactly as the trade page's Levels panel does today.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend test -- --include src/app/workspaces/trades/why/levels-block.spec.ts --include src/app/ui/primitives.spec.ts --watch=false`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/trades/why/levels-block.ts frontend/src/app/workspaces/trades/why/levels-block.spec.ts
git commit -m "feat(ui): v151 order-ready levels block (V151-10)"
```

