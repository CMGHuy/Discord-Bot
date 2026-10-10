# v148 Ops hardening, part 5b: System → Scan health panels, full suites, production rollout (OH22–OH24)

> **For agentic workers:** pull one task at a time (`grep -n "^### Task OH22:" -A 320 <this file>`), never this file whole.

**Spec:** `docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md` (§ "Admin surface", § Testing, § Parallelisation "After merge and deploy", § O3 "Mirroring")
**Index:** `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md`. Its Global Constraints, Parallelisation and task ledger are binding here and are not repeated. Part 5 (`_5-cron-admin-ui-suite.md`, OH19–OH21) was split here only to keep each file under 1500 lines.
**Bump:** ui patch · bot patch (applied at close-out, never by a task)
**Edge:** none (integrity)

`$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening`. Never `cd`; use absolute paths and `git -C $WT`. Frontend runs use `npm --prefix $WT/frontend test -- --include <spec>`.

Contracts consumed (ledger, final): OH20's payload `{providers, thresholds, swallowed, bot_counts_since}`; OH21's TS types `ProviderHealthRow`, `SwallowedRow`, `SystemHealth`, and the `SystemStore` signals `health()` and `healthError()`, refreshed by `resolveScan()` on the route's `scan`/`bot` events; OH19's scripts `scripts/ops/heartbeat_watch.sh` and `scripts/ops/install_heartbeat_watch_cron.sh`; OH5's `.env` key `OPS_ALERT_WEBHOOK_URL`.

# Phase E (continued) — panels, full suites, production rollout

### Task OH22: Provider-health and swallowed-errors panels

**Model:** sonnet — two presentational standalone components with pure row-shaping functions and DOM specs, plus a template edit; the accessibility rule (breach marked by text, not colour alone) and the null-is-dash rule need care.

**Files:**
- Create: `frontend/src/app/workspaces/system/provider-health-panel.ts`
- Create: `frontend/src/app/workspaces/system/provider-health-panel.spec.ts`
- Create: `frontend/src/app/workspaces/system/swallowed-errors-panel.ts`
- Create: `frontend/src/app/workspaces/system/swallowed-errors-panel.spec.ts`
- Modify: `frontend/src/app/workspaces/system/scan-tab.ts` (imports, `imports:` array at line 43, template after the "Bot process" panel)

**Why:** spec § "Admin surface": "two new standalone components, `provider-health-panel.ts` (a table of the 20 scans, newest first, a threshold breach marked with the existing danger token plus text, not colour alone) and `swallowed-errors-panel.ts` (sorted by count, process column, relative 'last seen')". Rows predating v148 "render as '—'". Both components take the store's `health()` as an input and fetch nothing themselves, so they need no `sb-async` (`ui/async-coverage.spec.ts` covers fetching panels only). The scan tab passes `store.health()` to both and shows `store.healthError()` beneath them.

Contract (ledger, final): selectors `sb-provider-health-panel` and `sb-swallowed-errors-panel`, classes `ProviderHealthPanel` and `SwallowedErrorsPanel`, each with input `health: SystemHealth | null`. The row shaping is exported as pure functions (`providerLines`, `rateText`, `breaches`, `swallowedLines`), so the specs pin the formatting without the DOM.

Rules the repo's source-scanning specs enforce, which these files must respect:
- `ui/primitives.spec.ts`: no local `.pos`, `.neg` or `.muted` rule, and no `.head`, `.row-link`, `.note` or `.chips` rule. The breach class is `.breach`, coloured with `var(--neg)` (the danger token the scan tab's own `.error` uses).
- `ui/breakpoint-guard.spec.ts`: no width media queries at all. The tables scroll inside `.scroll { overflow-x: auto; }`.
- `ui/contrast.spec.ts` / `tokens.css`: `--text-faint` is a rule colour, never text. Secondary text uses `--text-secondary`.
- `.num` (mono, tabular figures) is a global class in `src/styles.css:54`. Do not redefine it.
- Breach comparison is **strictly above** `pct / 100`, the same comparison `ops_watch.provider_verdict` alerts on (spec O4). An unknown rate never breaches.

- [ ] **Step 1: Write the failing specs**

Create `$WT/frontend/src/app/workspaces/system/provider-health-panel.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SystemHealth } from '../../api/models';
import {
  ProviderHealthPanel,
  breaches,
  providerLines,
  rateText,
} from './provider-health-panel';

const ROW = {
  at: '2026-10-09T14:05:00+00:00',
  tickers: 150,
  provider_fallback_rate: 0.04,
  stale_symbols: 1,
  empty_symbols: 2,
  empty_rate: 2 / 150,
};

const HEALTH: SystemHealth = {
  providers: [
    { ...ROW, at: '2026-10-09T14:10:00+00:00', provider_fallback_rate: 0.25,
      empty_symbols: 12, empty_rate: 0.08 },
    ROW,
    { at: '2026-10-09T14:00:00+00:00', tickers: 150, provider_fallback_rate: null,
      stale_symbols: null, empty_symbols: null, empty_rate: null },
  ],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  swallowed: [],
  bot_counts_since: null,
};

function render(health: SystemHealth | null): HTMLElement {
  const fixture = TestBed.createComponent(ProviderHealthPanel);
  fixture.componentRef.setInput('health', health);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('provider health formatting', () => {
  it('renders a fraction as an unsigned one-decimal percentage', () => {
    expect(rateText(0.04)).toBe('4.0%');
    expect(rateText(0)).toBe('0.0%');
  });

  it('renders an unknown rate as an em dash, never as 0%', () => {
    expect(rateText(null)).toBe('—');
    expect(rateText(undefined)).toBe('—');
  });

  it('breaches strictly above the threshold, as the bot alerts', () => {
    expect(breaches(0.21, 20)).toBe(true);
    expect(breaches(0.2, 20)).toBe(false);
    expect(breaches(null, 20)).toBe(false);
  });

  it('keeps the server order and carries pre-v148 rows as dashes', () => {
    const lines = providerLines(HEALTH);

    expect(lines).toHaveLength(3);
    expect(lines[0]).toMatchObject({ fallback: '25.0%', fallbackBreach: true, emptyBreach: true });
    expect(lines[1]).toMatchObject({ fallbackBreach: false, empty: '2 (1.3%)', stale: '1' });
    expect(lines[2]).toMatchObject({
      fallback: '—', empty: '—', stale: '—', fallbackBreach: false, emptyBreach: false,
    });
  });

  it('has no lines before the first answer', () => {
    expect(providerLines(null)).toEqual([]);
  });
});

describe('ProviderHealthPanel', () => {
  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection()],
  }));

  it('renders one row per scan', () => {
    expect(render(HEALTH).querySelectorAll('tbody tr')).toHaveLength(3);
  });

  it('marks a breach with text as well as colour', () => {
    const cells = render(HEALTH).querySelectorAll('td.breach');

    expect(cells).toHaveLength(2);
    cells.forEach((cell) => expect(cell.textContent).toContain('over limit'));
  });

  it('names the alert thresholds it marks against', () => {
    const text = render(HEALTH).textContent ?? '';

    expect(text).toContain('above 20%');
    expect(text).toContain('above 5%');
  });

  it('says so when no scan is recorded', () => {
    const el = render({ ...HEALTH, providers: [] });

    expect(el.querySelector('table')).toBeNull();
    expect(el.textContent).toContain('No scan recorded yet');
  });
});
```

Create `$WT/frontend/src/app/workspaces/system/swallowed-errors-panel.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SystemHealth } from '../../api/models';
import { SwallowedErrorsPanel, swallowedLines } from './swallowed-errors-panel';

const NOW = Date.parse('2026-10-10T12:00:00Z');

const HEALTH: SystemHealth = {
  providers: [],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  swallowed: [
    { process: 'admin', tag: 'runstate.read_heartbeat', count: 1,
      first_at: '2026-10-10T11:00:00Z', last_at: '2026-10-10T11:00:00Z',
      last_error: 'OperationalError: connection refused' },
    { process: 'bot', tag: 'scan.run_bounded', count: 7,
      first_at: '2026-10-10T06:05:00Z', last_at: '2026-10-10T09:00:00Z',
      last_error: 'TimeoutError: cold-fetch chunk 3' },
    { process: 'bot', tag: 'marketdata.price_batch', count: 7,
      first_at: null, last_at: null, last_error: null },
  ],
  bot_counts_since: '2026-10-10T06:00:00Z',
};

function render(health: SystemHealth | null): HTMLElement {
  const fixture = TestBed.createComponent(SwallowedErrorsPanel);
  fixture.componentRef.setInput('health', health);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('swallowed error rows', () => {
  it('sorts by count, then process, then tag', () => {
    expect(swallowedLines(HEALTH, NOW).map((l) => l.tag)).toEqual([
      'marketdata.price_batch',
      'scan.run_bounded',
      'runstate.read_heartbeat',
    ]);
  });

  it('shows last seen as a relative age', () => {
    const lines = swallowedLines(HEALTH, NOW);

    expect(lines.find((l) => l.tag === 'scan.run_bounded')!.lastSeen).toBe('3h ago');
    expect(lines.find((l) => l.tag === 'runstate.read_heartbeat')!.lastSeen).toBe('1h ago');
  });

  it('renders an unknown time or error as an em dash', () => {
    const line = swallowedLines(HEALTH, NOW).find((l) => l.tag === 'marketdata.price_batch')!;

    expect(line.lastSeen).toBe('—');
    expect(line.lastError).toBe('—');
  });

  it('has no lines before the first answer', () => {
    expect(swallowedLines(null)).toEqual([]);
  });
});

describe('SwallowedErrorsPanel', () => {
  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection()],
  }));

  it('renders one row per process and tag, with the process named', () => {
    const rows = render(HEALTH).querySelectorAll('tbody tr');

    expect(rows).toHaveLength(3);
    expect(rows[2].textContent).toContain('admin');
    expect(rows[0].textContent).toContain('bot');
  });

  it('says when the bot counts began', () => {
    expect(render(HEALTH).textContent).toContain('Bot counts since');
  });

  it('says so when the bot has not reported counts yet', () => {
    const el = render({ ...HEALTH, bot_counts_since: null });

    expect(el.textContent).toContain('has not reported its counts yet');
  });

  it('says so when nothing was swallowed', () => {
    const el = render({ ...HEALTH, swallowed: [] });

    expect(el.querySelector('table')).toBeNull();
    expect(el.textContent).toContain('None since the processes started');
  });
});
```

- [ ] **Step 2: Run them and watch them fail**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
npm --prefix $WT/frontend test -- --include src/app/workspaces/system/provider-health-panel.spec.ts
npm --prefix $WT/frontend test -- --include src/app/workspaces/system/swallowed-errors-panel.spec.ts
```

Expected: both fail to compile, because `./provider-health-panel` and `./swallowed-errors-panel` do not exist.

- [ ] **Step 3: Write the provider panel**

Create `$WT/frontend/src/app/workspaces/system/provider-health-panel.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ProviderHealthRow, SystemHealth } from '../../api/models';
import { ABSENT, dateTime, num, share } from '../../ui/format';
import { Panel } from '../../ui/layout';

/** One rendered row. The text is built here rather than in the template so
 *  the spec can pin "unknown renders —, never 0%" without a DOM. */
export interface ProviderHealthLine {
  at: string;
  tickers: string;
  fallback: string;
  fallbackBreach: boolean;
  empty: string;
  emptyBreach: boolean;
  stale: string;
}

const isKnown = (value: number | null | undefined): value is number =>
  value !== null && value !== undefined;

/** A fraction as an unsigned percentage with one decimal; unknown → "—".
 *  `share`, not `pct`: a rate is a level, not a gain or a loss. */
export function rateText(rate: number | null | undefined): string {
  return isKnown(rate) ? share(rate * 100, 1) : ABSENT;
}

/** The comparison the bot alerts on (`ops_watch.provider_verdict`): strictly
 *  above `pct / 100`. An unknown rate never breaches. */
export function breaches(rate: number | null | undefined, pct: number): boolean {
  return isKnown(rate) && rate > pct / 100;
}

function emptyText(row: ProviderHealthRow): string {
  return isKnown(row.empty_symbols)
    ? `${num(row.empty_symbols, 0)} (${rateText(row.empty_rate)})`
    : ABSENT;
}

/** Server order (newest first) is kept. */
export function providerLines(health: SystemHealth | null): ProviderHealthLine[] {
  if (!health) return [];
  const { fallback_pct, empty_pct } = health.thresholds;
  return health.providers.map((row) => ({
    at: dateTime(row.at),
    tickers: num(row.tickers, 0),
    fallback: rateText(row.provider_fallback_rate),
    fallbackBreach: breaches(row.provider_fallback_rate, fallback_pct),
    empty: emptyText(row),
    emptyBreach: breaches(row.empty_rate, empty_pct),
    stale: num(row.stale_symbols, 0),
  }));
}

/**
 * v148 — the last 20 scans' provider figures, newest first.
 *
 * A breach is marked in the danger colour AND with the words "over limit":
 * colour alone fails anyone who cannot tell the red apart, and this is the
 * table someone reads to decide whether the data feed is broken.
 */
@Component({
  selector: 'sb-provider-health-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Data providers">
      <p class="explain">
        Recent scans, newest first. The ops channel is alerted when fallback is above {{ fallbackPct() }}% or empty is above {{ emptyPct() }}% of a scan.
        Stale counts frames whose last bar is older than the previous NYSE session; it is shown here, not alerted on.
      </p>
      @if (lines().length) {
        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Scan</th>
                <th scope="col" class="right">Tickers</th>
                <th scope="col" class="right">Fallback</th>
                <th scope="col" class="right">Empty</th>
                <th scope="col" class="right">Stale</th>
              </tr>
            </thead>
            <tbody>
              @for (line of lines(); track $index) {
                <tr>
                  <td>{{ line.at }}</td>
                  <td class="num right">{{ line.tickers }}</td>
                  <td class="num right" [class.breach]="line.fallbackBreach">{{ line.fallback }}@if (line.fallbackBreach) {<span class="flag"> · over limit</span>}</td>
                  <td class="num right" [class.breach]="line.emptyBreach">{{ line.empty }}@if (line.emptyBreach) {<span class="flag"> · over limit</span>}</td>
                  <td class="num right">{{ line.stale }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="explain">No scan recorded yet.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .explain {
      max-width: 72ch;
      margin: 0 0 var(--space-10);
      color: var(--text-secondary);
      font-size: var(--text-table);
      line-height: 1.5;
    }
    .scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      font-weight: 500;
      text-align: left;
      white-space: nowrap;
    }
    td {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text);
      white-space: nowrap;
    }
    .right { text-align: right; }
    .breach { color: var(--neg); font-weight: 600; }
  `,
})
export class ProviderHealthPanel {
  readonly health = input<SystemHealth | null>(null);

  protected readonly lines = computed(() => providerLines(this.health()));
  protected readonly fallbackPct = computed(() => this.health()?.thresholds.fallback_pct ?? ABSENT);
  protected readonly emptyPct = computed(() => this.health()?.thresholds.empty_pct ?? ABSENT);
}
```

Keep each `{{ … }}%` on the same line as the word before it ("above {{ fallbackPct() }}%"). The spec reads `textContent` for `above 20%`.

- [ ] **Step 4: Write the swallowed-errors panel**

Create `$WT/frontend/src/app/workspaces/system/swallowed-errors-panel.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { SwallowedRow, SystemHealth } from '../../api/models';
import { ABSENT, age, dateTime, num } from '../../ui/format';
import { Panel } from '../../ui/layout';

export interface SwallowedLine {
  process: string;
  tag: string;
  count: string;
  lastSeen: string;
  /** Full timestamp, for the cell's tooltip. */
  lastSeenAt: string;
  lastError: string;
}

const byCount = (a: SwallowedRow, b: SwallowedRow): number =>
  b.count - a.count || a.process.localeCompare(b.process) || a.tag.localeCompare(b.tag);

function lastSeen(iso: string | null, now: number): string {
  const ago = age(iso, now);
  return ago === ABSENT ? ABSENT : `${ago} ago`;
}

/** Highest count first; ties by process, then tag, so a refresh never
 *  reshuffles equal rows. */
export function swallowedLines(health: SystemHealth | null, now = Date.now()): SwallowedLine[] {
  if (!health) return [];
  return [...health.swallowed].sort(byCount).map((row) => ({
    process: row.process,
    tag: row.tag,
    count: num(row.count, 0),
    lastSeen: lastSeen(row.last_at, now),
    lastSeenAt: dateTime(row.last_at),
    lastError: row.last_error ?? ABSENT,
  }));
}

/**
 * v148 — errors the bot and the admin caught and carried on from, per call
 * site. A non-zero count is not an outage. It is the place a silent
 * failure (the 2026-09-14 lxml outage sat inside one of these) becomes
 * visible before anything downstream looks wrong.
 */
@Component({
  selector: 'sb-swallowed-errors-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Swallowed errors">
      <p class="explain">
        Errors the bot and the admin caught and carried on from, counted per call site. Counts start at zero when a process starts.
        {{ sinceText() }}
      </p>
      @if (lines().length) {
        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Process</th>
                <th scope="col">Call site</th>
                <th scope="col" class="right">Count</th>
                <th scope="col">Last seen</th>
                <th scope="col">Last error</th>
              </tr>
            </thead>
            <tbody>
              @for (line of lines(); track line.process + ':' + line.tag) {
                <tr>
                  <td>{{ line.process }}</td>
                  <td class="num">{{ line.tag }}</td>
                  <td class="num right">{{ line.count }}</td>
                  <td [attr.title]="line.lastSeenAt">{{ line.lastSeen }}</td>
                  <td class="last-error">{{ line.lastError }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="explain">None since the processes started.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .explain {
      max-width: 72ch;
      margin: 0 0 var(--space-10);
      color: var(--text-secondary);
      font-size: var(--text-table);
      line-height: 1.5;
    }
    .scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      font-weight: 500;
      text-align: left;
      white-space: nowrap;
    }
    td {
      padding: var(--space-6) var(--space-8);
      border-bottom: 1px solid var(--border);
      color: var(--text);
      white-space: nowrap;
    }
    .right { text-align: right; }
    .last-error { min-width: 24ch; color: var(--text-secondary); white-space: normal; }
  `,
})
export class SwallowedErrorsPanel {
  readonly health = input<SystemHealth | null>(null);

  protected readonly lines = computed(() => swallowedLines(this.health()));
  protected readonly sinceText = computed(() => {
    const since = this.health()?.bot_counts_since;
    return since
      ? `Bot counts since ${dateTime(since)}.`
      : 'The bot has not reported its counts yet.';
  });
}
```

`lines` is recomputed whenever `health` changes, which happens on every `scan`/`bot` refresh, so "last seen" stays current enough without a timer.

- [ ] **Step 5: Put both panels on the Scan tab**

In `$WT/frontend/src/app/workspaces/system/scan-tab.ts`:

1. After `import { Toolbar, ToolbarControl } from '../../ui/toolbar';`, add:

```ts
import { ProviderHealthPanel } from './provider-health-panel';
import { SwallowedErrorsPanel } from './swallowed-errors-panel';
```

2. Replace `imports: [Panel, Button, ConfirmDialog, Toolbar, Freshness],` with:

```ts
  imports: [
    Panel, Button, ConfirmDialog, Toolbar, Freshness, ProviderHealthPanel, SwallowedErrorsPanel,
  ],
```

3. The template has exactly one place where a `</sb-panel>` is followed by a blank line and `<sb-confirm-dialog`: the end of the "Bot process" panel. Replace

```html
    </sb-panel>

    <sb-confirm-dialog
```

with

```html
    </sb-panel>

    <sb-provider-health-panel [health]="store.health()" />
    <sb-swallowed-errors-panel [health]="store.health()" />
    @if (store.healthError(); as message) {
      <p class="error" role="alert">Health panels: {{ message }}</p>
    }

    <sb-confirm-dialog
```

The tab's `:host` is a one-column grid with `gap: var(--section-gap)`, so the two panels stack under "Bot process" with the existing spacing and need no new style. `.error` is the tab's own existing class.

- [ ] **Step 6: Run the specs and the repo-wide source gates**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
npm --prefix $WT/frontend test -- --include src/app/workspaces/system/provider-health-panel.spec.ts
npm --prefix $WT/frontend test -- --include src/app/workspaces/system/swallowed-errors-panel.spec.ts
npm --prefix $WT/frontend test -- --include src/app/workspaces/system/scan-tab.spec.ts
npm --prefix $WT/frontend test -- --include src/app/ui/primitives.spec.ts
npm --prefix $WT/frontend test -- --include src/app/ui/breakpoint-guard.spec.ts
npm --prefix $WT/frontend test -- --include src/app/stores/system.store.spec.ts
npm --prefix $WT/frontend run build
```

Expected: every spec passes, with 0 failed. `ng build` finishes without template type errors. If the build fails only on a bundle budget, report the size to the controller and do not raise the budget. If a `textContent` assertion fails on whitespace, check that the template keeps `above {{ fallbackPct() }}%` on one line. Do not loosen the assertion.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add frontend/src/app/workspaces/system/provider-health-panel.ts frontend/src/app/workspaces/system/provider-health-panel.spec.ts frontend/src/app/workspaces/system/swallowed-errors-panel.ts frontend/src/app/workspaces/system/swallowed-errors-panel.spec.ts frontend/src/app/workspaces/system/scan-tab.ts
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH22: provider-health and swallowed-errors panels on System -> Scan"
```

### Task OH23: Full suites

**Model:** haiku — runs fixed commands and reports verdicts; any failure goes back to the task that owns the file, never fixed here.

**Files:** none modified, unless a failure is traced to its owning task, which then gets its own fix commit under that task's id.

**Why:** spec § Testing: "The plan's last task runs `python scripts/dev/testrun.py full` and `cd frontend && npm test` once each." This is the plan's only full-suite run (CLAUDE.md: "Full suite once per plan, as its final task"). It is also the last repo task before merge. Close-out (`/close-out`) applies the bump after it is green. OH24 runs after merge and deploy.

- [ ] **Step 1: Every task has landed**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
git -C $WT status --short
for id in OH2 OH3 OH4 OH5 OH6 OH7 OH8 OH9 OH10 OH11 OH12 OH13 OH14 OH15 OH16 OH17 OH18 OH19 OH20 OH21 OH22; do
  git -C $WT log --oneline main..HEAD | grep -q "v148 $id:" || echo "MISSING $id"
done
```

Expected: `git status --short` prints nothing (clean tree) and no `MISSING` line. OH1 has no branch commit, because its finding lives in the index's § Progress on `main`. Check it there: `grep -n "^OH1:" /home/user/Discord-Bot/docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` prints the finding. If anything is missing, stop and report it to the controller.

- [ ] **Step 2: Invariants the spec fixes**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
git -C $WT diff --stat main...HEAD -- docker-compose.yml .github/workflows/deploy.yml
git -C $WT grep -n -E "^\s*(import gunicorn|from gunicorn)" -- tests admin_ui.py admin_wsgi.py deploy/gunicorn.conf.py swingbot || true
git -C $WT grep -n "from \.loops import\|from swingbot.commands.scanning.loops import" -- swingbot/commands/scanning/ops_watch.py || true
git -C $WT diff --name-only main...HEAD -- VERSION.json
python -m py_compile $WT/admin_ui.py $WT/admin_wsgi.py $WT/deploy/gunicorn.conf.py $WT/bot.py && echo "compile ok"
```

Expected: the first four commands print nothing. Compose and CI are untouched (O1), no file imports gunicorn, `ops_watch` has no module-level import from `loops` (index constraint 7), and no task touched `VERSION.json`. The last line prints `compile ok`.

- [ ] **Step 3: Complexity over every changed Python file**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
FILES=$(git -C $WT diff --name-only --diff-filter=AM main...HEAD -- '*.py' | sed "s#^#$WT/#")
python -m radon cc -s -n C $FILES > /tmp/claude-oh23-cc-after.txt; cat /tmp/claude-oh23-cc-after.txt
mkdir -p /tmp/claude-oh23-before
for f in $(git -C $WT diff --name-only --diff-filter=M main...HEAD -- '*.py'); do
  mkdir -p /tmp/claude-oh23-before/$(dirname $f); git -C $WT show main:$f > /tmp/claude-oh23-before/$f
done
python -m radon cc -s -n C $(find /tmp/claude-oh23-before -name '*.py') > /tmp/claude-oh23-cc-before.txt; cat /tmp/claude-oh23-cc-before.txt
```

Expected: every function listed "after" is also listed "before", with the same or a higher score. These are legacy functions at or above C, which a conversion never made worse. Nothing new appears, and none of the files the plan created (`swallowed.py`, `login_limiter.py`, `ops_watch.py`, `ops_health.py`, `admin_wsgi.py`, `deploy/gunicorn.conf.py`, and the tests) is listed. Report any function that is new or worse to the controller, together with the task that owns its file.

- [ ] **Step 4: The full Python suite (one run)**

Dispatch the `test-runner` subagent (so its output stays out of this context) with:

```bash
python /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/scripts/dev/testrun.py full
```

Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`). A test that skips for want of the test database is not green: start `db-test` and run again. On a failure, read the failing test's file and trace it to the task whose files it covers (index ledger). Fix it under that task's id, commit (`v148 OH<n>: fix <what>`), and rerun only that file with `testrun.py file`. Do not rerun the full suite for a one-file fix unless the fix touched shared code (`swallowed.py`, `fetch.py`, `runstate.py`, `heartbeat.py`, `config.py`). In that case, run `full` once more.

- [ ] **Step 5: The full frontend suite (one run)**

```bash
npm --prefix /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/frontend test
```

Expected: every spec file passes, with 0 failed. The same rule applies to a failure: trace it to OH4, OH21 or OH22, fix it under that id, and rerun the one spec with `--include`.

- [ ] **Step 6: Report**

Nothing to commit unless Step 4 or 5 needed a fix, and each fix was committed under its owning task. Hand the controller one line per suite, for the index's § Progress (the controller commits it on `main`):

```
OH23: python full <N> passed, 0 failed, 0 xfailed (<duration>); frontend <N> passed, 0 failed; radon: no new or worse function. Ready for merge, deploy, then OH24.
```

The bump (`ui` patch, `bot` patch) is applied by `/close-out` after OH24, never here.

### Task OH24: Production rollout (post-deploy)

**Model:** sonnet — scripted production checks through one SSH wrapper with fixed expected outputs; two partner confirmations; it changes one `.env` value and one crontab line, both mirrored already.

**Files:** none in the repo. Production only: the VM's `.env` (`OPS_ALERT_WEBHOOK_URL`, through `scripts/ops/env_set.py`) and root's crontab (through `scripts/ops/install_heartbeat_watch_cron.sh`). The index's § Progress block on `main` records the result, and the controller commits it.

**Why:** spec § O3 "Mirroring" and § Parallelisation "After merge and deploy": "set `OPS_ALERT_WEBHOOK_URL`, install the cron, confirm one healthy verdict and a test post; confirm the admin process is gunicorn … and the login works through the tunnel." Spec: "The prod-side task is not done until the cron has logged one healthy verdict and a forced test post (`--test`) has reached the channel." Nothing here touches eToro, orders, trades or plans. It is ops plumbing only.

**Rules for this task (CLAUDE.md, `mirror-prod` skill):**
- Every command goes through `bash scripts/ops/ssh-hetzner.sh "<cmd>"` from the dev machine's main tree, or pipes a script into `bash scripts/ops/ssh-hetzner.sh "bash -s"`. Never use a raw `ssh`/`scp`, never another key path, and never `sed -i` on the VM's `.env`. `ssh-hetzner.sh` is uncommitted and exists only on the partner's WSL setup. If `ls /home/user/Discord-Bot/scripts/ops/ssh-hetzner.sh` fails in this session, stop and hand this task back to the controller to run in a session that has it.
- **Mirroring is already complete:** both scripts (OH19), the `.env.example` key (OH5) and the `DEPLOY_HETZNER.md` row (OH19) are on `main` before anything here runs. The only production-only values are the webhook URL, which is a secret and is never committed, and the crontab line, which the committed installer writes verbatim. If anything here forces a change to a committed file, that change goes back into the repo and is committed before this task counts as done.
- The webhook URL is a secret. Never print it in full. Every read-back below masks it.
- Do **not** test the login limiter on production with five bad passwords. It would lock the partner out for 15 minutes. `test_login_limiter.py` covers the limiter.

- [ ] **Step 0: Preconditions — merged, deployed, scripts present**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" <<'EOF'
set -e
cd /opt/swing-bot
git log -1 --format='%h %s'
tail -n 1 backups/deploys.jsonl
ls -l scripts/ops/heartbeat_watch.sh scripts/ops/install_heartbeat_watch_cron.sh admin_wsgi.py deploy/gunicorn.conf.py
grep -c '^OPS_ALERT_WEBHOOK_URL=' .env || true
docker compose ps --format '{{.Service}} {{.State}} {{.Health}}'
EOF
```

Expected: the VM's HEAD is the merge of `2026-10-09-v148-ops-hardening` (or later), and the last `deploys.jsonl` line names that sha. All four files exist. `bot`, `admin` and `db` are `running`, and `admin` is `healthy`. The `grep -c` prints `0` (key not set yet) or `1` (set earlier). If the deploy is not on the v148 merge, stop: this task runs after deploy only.

- [ ] **Step 1: The admin runs under gunicorn, and its request lines still reach `admin.log`**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" <<'EOF'
cd /opt/swing-bot
docker compose exec -T admin sh -c 'ps -eo pid,args 2>/dev/null || for p in /proc/[0-9]*; do printf "%s " "${p#/proc/}"; tr "\0" " " < "$p/cmdline"; echo; done' | grep -v "^ *$" | grep -E "gunicorn|admin_ui|python" || true
docker compose logs --since 2h admin 2>&1 | grep -E "Booting worker|Listening at|Using worker" | tail -n 5
curl -fsS -o /dev/null -w "local / -> %{http_code}\n" http://127.0.0.1:1234/ || echo "local / unreachable"
tail -n 200 logs/admin.log | grep -cE '"(GET|POST) /' || true
EOF
```

Expected:
- The process list shows `python -m gunicorn -c /app/deploy/gunicorn.conf.py admin_wsgi:app` twice, once for the master and once for its single worker. No line shows `admin_ui.py` running `app.run`, and there is no second worker.
- The logs show `Listening at: http://0.0.0.0:1234`, `Using worker: gthread` and one `Booting worker with pid`.
- `local / -> 200` (or `302` to the SPA). If port 1234 is bound to the container network only and the curl reports unreachable, the healthy `admin` state from Step 0 is the same check.
- A non-zero count of request lines in `logs/admin.log`, which proves the `gunicorn.access` wiring from OH2.

If the admin is running `app.run`, the image lacks gunicorn: check `docker compose exec -T admin python -c "import importlib.util as u; print(u.find_spec('gunicorn'))"`. If it crash-loops, roll back per `docs/deploy/DEPLOY_HETZNER.md` § Rolling back (the image swaps and compose stays `python admin_ui.py`), then stop and report.

- [ ] **Step 2: The bot writes its new heartbeat keys, and the watchdog is quiet**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" <<'EOF'
cd /opt/swing-bot
docker compose exec -T db psql -U swingbot -d swingbot -tA -c "SELECT doc ? 'swallowed', doc->'swallowed'->>'since', doc->>'timestamp', floor(extract(epoch FROM now() - (doc->>'timestamp')::timestamptz)) FROM bot_heartbeat WHERE key = 'bot'" </dev/null
docker compose logs --since 2h bot 2>&1 | grep -cE "scan watchdog tick failed|provider health check failed" || true
EOF
```

Expected: `t|<bot boot iso>|<recent iso>|<age in seconds, below 900>`, and a count of `0`. If the age is large and the market is closed, that is still wrong: the heartbeat is written every tick, whatever the session. Stop and report it.

- [ ] **Step 3: Get the ops-channel webhook from the partner**

Ask with `AskUserQuestion`, one question, recommended option first:

> "The heartbeat cron needs a Discord webhook for the ops channel (Channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL). How do you want to provide it?"
> 1. **(Recommended)** "I'll paste the URL here. Set it with `env_set.py`, and only a masked version is printed back."
> 2. "I'll set it myself in the admin (System → Settings → Data Sources → the ops alert webhook field), then tell you."
> 3. "Reuse an existing webhook URL already in `.env` (name the key)."

For option 1, run (`<URL>` is the pasted value, single-quoted):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py OPS_ALERT_WEBHOOK_URL '<URL>' >/dev/null && echo set"
```

For option 3, copy the named key's value on the VM without printing it:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py OPS_ALERT_WEBHOOK_URL \"\$(python3 scripts/ops/env_set.py --get <KEY>)\" >/dev/null && echo set"
```

Then, whichever option was chosen, read it back masked:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && python3 scripts/ops/env_set.py --get OPS_ALERT_WEBHOOK_URL | sed -E 's#(https://[^/]+/api/webhooks/[0-9]+/).+#\1***#'"
```

Expected: `https://discord.com/api/webhooks/<id>/***` (or `discordapp.com`). No container restart is needed. The key is `hot_reloadable=False` because no process reads it, and the cron reads `.env` fresh on every run. `env_set.py` writes in place and snapshots `.env` (v116), so this is the whole production edit.

- [ ] **Step 4: Install the cron**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_heartbeat_watch_cron.sh
```

Expected: the printed crontab contains, exactly once each:

```
# v148 heartbeat watch (installed by install_heartbeat_watch_cron.sh)
*/5 * * * * /usr/bin/env bash /opt/swing-bot/scripts/ops/heartbeat_watch.sh >/dev/null 2>> /opt/swing-bot/logs/heartbeat_watch.log
```

Every pre-existing line (the PITR crons, `backup_db.sh` and the rest) is still there. Compare it with `bash scripts/ops/ssh-hetzner.sh "crontab -l"` taken before this step if in doubt. The installer reads from the local main tree, which is the same committed file the VM has.

- [ ] **Step 5: A dry run, one real healthy verdict, and the forced test post**

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" <<'EOF'
set -e
W=/opt/swing-bot/scripts/ops/heartbeat_watch.sh
bash $W --dry-run --age 30
bash $W
bash $W --test
cat /opt/swing-bot/logs/heartbeat_watch.state
wc -l < /opt/swing-bot/logs/heartbeat_watch.log
EOF
```

Expected, in order:
- `… verdict=ok age_s=30 threshold_s=900 previous=none action=none dry_run=1`. The threshold is 900 unless `SCAN_INTERVAL_MINUTES` is above 5, in which case it is 3 × the interval × 60.
- `… verdict=ok age_s=<below threshold> threshold_s=… previous=none action=none`. This is the first real healthy verdict: it read Postgres through `docker compose exec`.
- `… test delivered=yes` (exit 0).
- The state file holds `ok`.
- A line count. Note it, because Step 7 compares against it.

If the real run says `verdict=unreadable`, run the query by hand: `cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -tA -c "SELECT doc->>'timestamp' FROM bot_heartbeat WHERE key = 'bot'"`. Fix the cause. A fix to the script goes back into the repo first (`mirror-prod`), never as a VM-only edit.

- [ ] **Step 6: The partner confirms the test post reached the channel**

Ask with `AskUserQuestion`: "A `[swingbot ops] heartbeat_watch TEST post …` message was just sent to the ops channel. Did it arrive?" Options: 1. **(Recommended)** "Yes, it's there." 2. "No, nothing arrived." If the answer is no, re-check the masked URL from Step 3 and run `--test` once more. Do not proceed until a post is confirmed.

- [ ] **Step 7: The cron logs its own healthy verdict**

The cron fires every 5 minutes. Do not foreground-`sleep`. Use the `Monitor` tool with an until-loop, or do Step 8 first and come back. Then:

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" <<'EOF'
wc -l < /opt/swing-bot/logs/heartbeat_watch.log
tail -n 3 /opt/swing-bot/logs/heartbeat_watch.log
grep -c "heartbeat_watch.sh" /var/log/syslog 2>/dev/null || journalctl -u cron --since "-15 min" 2>/dev/null | grep -c heartbeat_watch || true
EOF
```

Expected: the line count is higher than Step 5's. The newest line is `… verdict=ok … action=none`, stamped at a minute divisible by 5 and after Step 5. The cron/syslog count is at least 1. No stderr noise follows the verdict lines in the log (the cron appends stderr there). Stderr noise means the script hit an error under cron's environment, usually PATH: report it.

- [ ] **Step 8: The partner checks the login through the tunnel, and the new panels**

Ask with `AskUserQuestion`: "Please sign in to the admin through its public (Cloudflare) address and open System → Scan. Did the sign-in work, and do you see the 'Data providers' and 'Swallowed errors' panels?" Options:
1. **(Recommended)** "Signed in; both panels show data."
2. "Signed in; the panels are there but empty or show an error."
3. "The sign-in failed."

Empty panels right after deploy are normal until the first scheduled scan of the session writes a v148 telemetry row, and older rows show "—". The swallowed table can legitimately read "None since the processes started". An error message under the panels, or a failed sign-in, is a stop: read `logs/admin.log` around the request and report.

- [ ] **Step 9: Record and hand back**

Append to the `## Progress` block of `/home/user/Discord-Bot/docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` (main tree; the controller commits it), filling in the observed values:

```
OH24 (<YYYY-MM-DD HH:MM> UTC): admin = gunicorn (master + 1 gthread worker), admin.log request lines present; heartbeat doc carries swallowed (since <iso>); OPS_ALERT_WEBHOOK_URL set via env_set.py (masked https://discord.com/api/webhooks/<id>/***); cron installed (*/5, marker v148); first healthy verdict <log line timestamp>; cron's own healthy verdict <log line timestamp>; --test delivered=yes, confirmed in channel by the partner; tunnel sign-in OK, both System -> Scan panels visible.
```

Nothing is committed on the branch in this task. Removing the cron, should that ever be needed: `bash scripts/ops/ssh-hetzner.sh "crontab -l | grep -vF heartbeat_watch | crontab -"`. A permanent removal needs its own spec (OH19 "Owner/Removal"). The plan is now ready for `/close-out`.

