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
