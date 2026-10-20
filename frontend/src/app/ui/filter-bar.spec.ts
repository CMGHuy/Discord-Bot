
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { FilterBar, FilterChips } from './filter-bar';
const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/filter-bar.ts'), 'utf8');
@Component({ imports: [FilterBar], template: `<sb-filter-bar [activeCount]="active()" [shown]="shown()" [total]="total()" (cleared)="onCleared()"><span class="projected">control</span></sb-filter-bar>` })
class Host { readonly active = signal(0); readonly shown = signal<number | null>(null); readonly total = signal<number | null>(null); cleared = 0; onCleared(): void { this.cleared += 1; } }
describe('FilterBar (v80 D4)', () => {
  let fixture: ComponentFixture<Host>; let host: Host;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }); fixture = TestBed.createComponent(Host); host = fixture.componentInstance; fixture.detectChanges(); });
  const el = () => fixture.nativeElement as HTMLElement;
  it('says nothing when none active', () => expect(el().querySelector('.summary')).toBeNull());
  it('states active count and remaining rows', () => { host.active.set(2); host.shown.set(12); host.total.set(40); fixture.detectChanges(); expect(el().querySelector('.active')!.textContent!.replace(/\s+/g, ' ').trim()).toBe('2 active · 12 of 40'); });
  it('shows count alone without total', () => { host.active.set(2); host.shown.set(12); fixture.detectChanges(); expect(el().querySelector('.active')!.textContent!.trim()).toBe('2 active'); });
  it('clears in one click', () => { host.active.set(1); fixture.detectChanges(); [...el().querySelectorAll('button')].find((b) => b.textContent!.includes('Clear all'))!.click(); expect(host.cleared).toBe(1); });
  it('projects controls into own row', () => { expect(el().querySelector('.bar .projected')).not.toBeNull(); expect(el().querySelector('sb-control-row')).toBeNull(); });
  it('uses a narrow container grid', () => { expect(SOURCE).toMatch(/:host \{[^}]*container: filter-bar \/ inline-size/); expect(SOURCE).toMatch(/@container filter-bar \(max-width: 639px\) \{\s*\.bar \{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/); });
  it('deprecates filter chips', () => expect(SOURCE).toMatch(/Deprecated \(v80 D4\)[\s\S]*sb-segmented/));
});

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) =>
  SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

describe('FilterBar with nothing to say (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('renders an empty bar when nothing is projected and nothing is active', () => {
    // Trades mounts <sb-filter-bar [activeCount]="…" /> with no projected
    // control; Angular leaves only comment nodes, which :empty ignores.
    const f = TestBed.createComponent(FilterBar);
    f.detectChanges();
    expect((f.nativeElement as HTMLElement).querySelector('.bar')!.matches(':empty')).toBe(true);
  });

  it('takes no room at all when the bar is empty', () => {
    // The empty bar used to keep its 2 x --space-10 padding and sit between
    // two section gaps: the ~60px hole above Trades' Sort select.
    expect(SOURCE).toMatch(/:host:has\(> \.bar:empty\) \{ display: none; \}/);
  });
});

describe('FilterChips on a phone (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('is one line that scrolls sideways, never a wrapped block', () => {
    const phone = SOURCE.match(/\/\* v179 chips \*\/\s*@media \(max-width: 639px\) \{([\s\S]*?)\n    \}/)?.[1] ?? '';
    expect(phone).toMatch(/:host \{ flex: 1 1 100%; \}/);
    expect(phone).toMatch(/\.chips \{[^}]*flex-wrap: nowrap;[^}]*overflow-x: auto;/);
  });

  it('never squeezes or wraps a chip label', () => {
    expect(rule('.chip')).toContain('flex: 0 0 auto');
    expect(rule('.chip')).toContain('white-space: nowrap');
  });

  it('sizes chips from --control-h like every other control on the row', () => {
    expect(rule('.chip')).toContain('min-height: var(--control-h)');
  });

  it('lets its host shrink inside a flex row', () => {
    expect(SOURCE).toMatch(/selector: 'sb-filter-chips'[\s\S]*?:host \{ display: block; min-width: 0; max-width: 100%; \}/);
  });

  it('still renders the All chip and every option', () => {
    const f = TestBed.createComponent(FilterChips);
    f.componentRef.setInput('chips', [{ value: 'open', label: 'Open' }, { value: 'closed', label: 'Closed' }]);
    f.detectChanges();
    const labels = [...(f.nativeElement as HTMLElement).querySelectorAll('.chip')].map((b) => b.textContent!.trim());
    expect(labels).toEqual(['All', 'Open', 'Closed']);
  });
});
