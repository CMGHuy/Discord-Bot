import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ControlBar } from './control-bar';
import { Field } from './field';
import { Select } from './form-controls';

@Component({
  imports: [ControlBar],
  template: `
    <sb-control-bar [activeCount]="count" (cleared)="cleared = true">
      <button filters id="chip">Open</button>
      <select scope id="range"><option>YTD</option></select>
    </sb-control-bar>
  `,
})
class Host {
  count = 0;
  cleared = false;
}

function host(count: number) {
  const f = TestBed.createComponent(Host);
  f.componentInstance.count = count;
  f.detectChanges();
  return f;
}

describe('ControlBar (v85 D22)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('projects filters into the leading slot', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.filters #chip')).not.toBeNull();
  });

  it('projects scope controls into the trailing slot', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.scope #range')).not.toBeNull();
  });

  it('hides Clear when nothing is filtered', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.clear')).toBeNull();
  });

  it('shows the active count when something is filtered', () => {
    const el = host(3).nativeElement as HTMLElement;
    expect(el.querySelector('.clear')!.textContent).toContain('3');
  });

  it('emits cleared when Clear is pressed', () => {
    const f = host(2);
    (f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.clear')!.click();
    expect(f.componentInstance.cleared).toBe(true);
  });

  it('names itself for assistive tech', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.bar')!.getAttribute('aria-label')).toBe('Page controls');
  });
});

const CONTROL_BAR_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/control-bar.ts'), 'utf8');

describe('ControlBar one row pattern (v179 §3.3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  // The phone block, whatever it contains, as one string.
  const phoneBlock = () =>
    CONTROL_BAR_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';

  it('stacks at the declared phone breakpoint, not one pixel into tablet', () => {
    // 640px is the first `sm` (tablet) width -- BREAKPOINTS.sm in breakpoints.ts.
    expect(CONTROL_BAR_SOURCE).toContain('@media (max-width: 639px)');
    expect(CONTROL_BAR_SOURCE).not.toContain('max-width: 640px');
  });

  it('lays phone filters out as two equal columns instead of a ragged wrap', () => {
    expect(phoneBlock()).toMatch(
      /\.filters \{[^}]*display: grid;[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
    );
  });

  it('keeps every projected control reachable -- the grid only re-arranges them', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.filters #chip')).not.toBeNull();
    expect(el.querySelector('.scope #range')).not.toBeNull();
  });
});

/* v195 Phase 2: Clear is the same quiet control as sb-filter-bar's ghost
 * "Clear all", not an accent link: the accent is for selected state. */
describe('ControlBar Clear is a quiet control (v195 Phase 2)', () => {
  const rule = (selector: string) =>
    CONTROL_BAR_SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';

  it('sets Clear in the secondary text on no fill, one control tall, 4px corners', () => {
    const clear = rule('.clear');
    for (const declaration of [
      'min-height: var(--control-h);',
      'min-width: var(--control-h);',
      'background: transparent;',
      'border: 0;',
      'border-radius: var(--control-radius);',
      'color: var(--text-secondary);',
      'font: inherit;',
      'font-size: var(--text-table);',
    ]) expect(clear, declaration).toContain(declaration);
    expect(clear).not.toContain('accent');
  });

  it('raises Clear on hover and rings it in the accent on keyboard focus only', () => {
    expect(rule('.clear:hover')).toContain('background: var(--surface-raised)');
    expect(rule('.clear:hover')).not.toContain('accent');
    expect(rule('.clear:focus-visible')).toContain('outline: 1px solid var(--accent)');
  });
});

@Component({
  imports: [ControlBar, Field, Select],
  template: `
    <sb-control-bar [activeCount]="1">
      <ng-container filters>
        <sb-field id="f-strategy" label="Strategy" size="m"><sb-select [options]="options" /></sb-field>
        <sb-field id="f-horizon" size="s"><sb-select ariaLabel="Horizon" [options]="options" /></sb-field>
      </ng-container>
      <ng-container scope>
        <sb-field id="f-units" label="Units" size="auto"><button type="button">R</button></sb-field>
      </ng-container>
    </sb-control-bar>
  `,
})
class FieldHost {
  readonly options = [{ value: 'rsi', label: 'RSI' }];
}

// jsdom has no layout; V246-18 measures these bottom edges in Chromium.
describe('ControlBar aligns fields on the bottom edge (v246 §A2)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });
  const rule = (selector: string) =>
    CONTROL_BAR_SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';
  const phoneBlock = () =>
    CONTROL_BAR_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';

  it('projects sb-field wrappers into both slots, Clear after the scope fields', () => {
    const f = TestBed.createComponent(FieldHost);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect([...el.querySelectorAll('.filters > sb-field')].map((n) => n.id)).toEqual(['f-strategy', 'f-horizon']);
    expect(el.querySelector('.scope > sb-field#f-units')).not.toBeNull();
    expect(el.querySelector('.scope > sb-field + .clear')).not.toBeNull();
  });
  it('aligns the bar and both groups along the bottom edge, never their centres', () => {
    expect(rule('.bar')).toContain('align-items: flex-end');
    expect(CONTROL_BAR_SOURCE).toMatch(/\.filters,\s*\.scope \{[^}]*align-items: flex-end;/);
    expect(CONTROL_BAR_SOURCE).not.toMatch(/align-items:\s*center/);
  });
  it('makes Clear exactly one control tall, the box every field ends in', () => {
    expect(rule('.clear')).toMatch(/\sheight: var\(--control-h\);/);
    expect(rule('.clear')).toContain('min-height: var(--control-h);');
  });
  it('fills each phone grid cell with its field and keeps the bottoms on one line', () => {
    const filters = phoneBlock().match(/\.filters \{[^}]*\}/)?.[0] ?? '';
    expect(filters).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))');
    expect(filters).toContain('align-items: end');
    expect(filters).toContain('justify-items: stretch');
    expect(phoneBlock()).toMatch(/\.bar \{ flex-direction: column; align-items: stretch; \}/);
  });
});
