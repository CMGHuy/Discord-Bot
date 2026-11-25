import { readFileSync } from 'node:fs'; import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core'; import { ComponentFixture, TestBed } from '@angular/core/testing'; import { beforeEach, describe, expect, it } from 'vitest';
import { SegmentOption, Segmented } from './segmented';
const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/segmented.ts'), 'utf8');
const OPTIONS: SegmentOption[] = [{ value: 'open', label: 'Open', count: 4 }, { value: 'partial', label: 'Partial' }, { value: 'closed', label: 'Closed', count: 12 }];
@Component({ imports: [Segmented], template: `<sb-segmented label="Status" [options]="options" [(value)]="value" />` }) class Host { readonly options = OPTIONS; readonly value = signal('open'); }
describe('Segmented (v80 D4)', () => {
  let fixture: ComponentFixture<Host>; let host: Host;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }); fixture = TestBed.createComponent(Host); host = fixture.componentInstance; fixture.detectChanges(); });
  const el = () => fixture.nativeElement as HTMLElement; const group = () => el().querySelector('[role=group]') as HTMLElement; const buttons = () => [...el().querySelectorAll('button')] as HTMLButtonElement[];
  const key = (value: string) => { group().dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true })); fixture.detectChanges(); };
  it('renders named real buttons', () => { expect(group().getAttribute('aria-label')).toBe('Status'); expect(buttons().map((b) => b.textContent!.replace(/\s+/g, ' ').trim())).toEqual(['Open 4', 'Partial', 'Closed 12']); });
  it('marks only selected option pressed', () => expect(buttons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false', 'false']));
  it('binds value two ways on click', () => { buttons()[2].click(); fixture.detectChanges(); expect(host.value()).toBe('closed'); });
  it('keeps one selected tab stop or first fallback', () => { expect(buttons().map((b) => b.tabIndex)).toEqual([0, -1, -1]); host.value.set('expired'); fixture.detectChanges(); expect(buttons().map((b) => b.tabIndex)).toEqual([0, -1, -1]); });
  it('moves and wraps with arrows and ends', () => { key('ArrowLeft'); expect(host.value()).toBe('closed'); key('Home'); expect(host.value()).toBe('open'); key('End'); expect(host.value()).toBe('closed'); });
  it('moves focus with selection', () => { buttons()[0].focus(); key('ArrowRight'); expect(document.activeElement).toBe(buttons()[1]); });
  it('has scrolling, nonwrapping touch-sized options', () => { expect(SOURCE).toMatch(/\.track \{[^}]*overflow-x: auto/); expect(SOURCE).toMatch(/\.segment \{[^}]*flex: 0 0 auto/); expect(SOURCE).toMatch(/\.segment \{[^}]*min-height: var\(--control-h\)/); });
});

/* v195 Phase 2: hover is the raised surface, and the accent tint marks the
 * selected segment only, so a hovered option never looks chosen. */
describe('Segmented is flat (v195 Phase 2)', () => {
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';

  it('raises an unselected segment on hover and keeps the accent for the selected one', () => {
    const hover = rule('.segment:not(.current):hover');
    expect(hover).toContain('color: var(--text);');
    expect(hover).toContain('background: var(--surface-raised);');
    expect(hover).not.toContain('accent');
    expect(rule('.current')).toContain('background: var(--accent-soft);');
    expect(SOURCE).not.toMatch(/\.segment:hover \{/);
  });
});

/* v246 §A2 "Phone": a group of three or more options takes the full row
 * below 640px, split into equal segments that never wrap. Two options keep
 * their natural width. jsdom resolves no media query, so the phone rule is
 * read from source (the pattern of control-bar.spec.ts). */
const TWO: SegmentOption[] = [{ value: 'compact', label: 'Compact' }, { value: 'full', label: 'Full' }];
@Component({ imports: [Segmented], template: `<sb-segmented label="Density" [options]="options()" [(value)]="value" />` })
class SizedHost { readonly options = signal<SegmentOption[]>(TWO); readonly value = signal('compact'); }

describe('Segmented on a phone (v246 §A2)', () => {
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }); });

  const PHONE = SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n {4}\}/)?.[1] ?? '';
  const phoneRule = (selector: string) =>
    PHONE.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} \\{[^}]*\\}`))?.[0] ?? '';

  function mount(options: SegmentOption[]) {
    const f = TestBed.createComponent(SizedHost);
    f.componentInstance.options.set(options);
    f.detectChanges();
    const debug = f.debugElement.query((d) => d.name === 'sb-segmented');
    return { f, host: debug.nativeElement as HTMLElement, segmented: debug.componentInstance as Segmented };
  }

  it('marks a group of three or more options as many', () => {
    const { host, segmented } = mount(OPTIONS);
    expect(segmented.many()).toBe(true);
    expect(host.classList).toContain('many');
  });

  it('leaves a two-option group at its natural width', () => {
    const { host, segmented } = mount(TWO);
    expect(segmented.many()).toBe(false);
    expect(host.classList).not.toContain('many');
  });

  it('follows the options: a group that grows to three becomes many', () => {
    const { f, host } = mount(TWO);
    f.componentInstance.options.set([...TWO, { value: 'roomy', label: 'Roomy' }]);
    f.detectChanges();
    expect(host.classList).toContain('many');
  });

  it('stretches a many group across its row below 640px, and only there', () => {
    expect(phoneRule(':host(.many)')).toContain('width: 100%');
    expect(phoneRule(':host(.many) .track')).toContain('display: flex');
    expect(phoneRule(':host(.many) .track')).toContain('width: 100%');
    // Outside the phone block the track stays inline-flex at its natural width.
    expect(SOURCE).toMatch(/\n {4}\.track \{ display: inline-flex;/);
  });

  it('splits the row into equal segments that keep the touch target', () => {
    const segment = phoneRule(':host(.many) .segment');
    expect(segment).toContain('flex: 1 1 0');
    expect(segment).toContain('min-width: var(--hit-min)');
    expect(SOURCE).toMatch(/\.segment \{[^}]*min-height: var\(--control-h\)/);
  });

  it('never wraps: a row too narrow for every option scrolls instead', () => {
    expect(SOURCE).not.toMatch(/flex-wrap:\s*wrap/);
    expect(SOURCE).toMatch(/\.track \{[^}]*overflow-x: auto/);
    expect(SOURCE).toMatch(/\.segment \{[^}]*white-space: nowrap/);
  });

  it('declares the phone block at 639px, not one pixel into tablet', () => {
    expect(SOURCE).toContain('@media (max-width: 639px)');
    expect(SOURCE).not.toContain('max-width: 640px');
  });
});
