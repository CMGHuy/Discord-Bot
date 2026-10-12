import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { SizingPanel } from './sizing-panel';

function mount(inputs: Record<string, unknown> = {}): ComponentFixture<SizingPanel> {
  const fixture = TestBed.createComponent(SizingPanel);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function rows(fixture: ComponentFixture<SizingPanel>): string[][] {
  return [...fixture.nativeElement.querySelectorAll('dl > div')].map((row: HTMLElement) =>
    [...row.querySelectorAll('dt, dd')].map(cell => cell.textContent!.replace(/\s+/g, ' ').trim()));
}

describe('SizingPanel', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('preserves the heading, snapshot help and four existing sizing rows', () => {
    const f = mount({ shares: 1234.4, positionValue: 12345.6, sizingMode: 'risk', workingStop: 98.5 });
    expect(f.nativeElement.querySelector('h2')?.textContent?.trim()).toBe('Sizing');
    expect(f.nativeElement.querySelector('.section-help')?.textContent?.replace(/\s+/g, ' ').trim())
      .toBe('Position size is snapshotted when the trade opens. A trade with no sizing snapshot was logged before that feature existed.');
    expect(rows(f).slice(0, 4)).toEqual([
      ['Shares', '1,234'], ['Deployed', '12,345.60'], ['Sizing mode', 'risk'], ['Working stop', '98.50'],
    ]);
  });

  it('puts unsigned gap risk with two decimals in the last row', () => {
    const f = mount({ gapP90Pct: 2.345 });
    expect(rows(f).at(-1)).toEqual(['Gap risk (p90)', '2.35%']);
    expect(rows(f)).toHaveLength(5);
    f.componentRef.setInput('gapP90Pct', 0);
    f.detectChanges();
    expect(rows(f).at(-1)).toEqual(['Gap risk (p90)', '0.00%']);
  });

  it('shows a fragile warning and explanatory tooltip for an explicit true flag', () => {
    const f = mount({ gapP90Pct: 2.5, gapFragile: true });
    const chip: HTMLElement = f.nativeElement.querySelector('dl > div:last-child sb-chip');
    expect(chip?.textContent?.trim()).toBe('fragile');
    expect(chip?.querySelector('.warn')).not.toBeNull();
    expect(chip?.getAttribute('title'))
      .toBe('The stop sits inside 90th-percentile gap noise: an overnight gap can jump it.');
  });

  it.each([false, null])('shows no warning when gapFragile is %s', gapFragile => {
    const f = mount({ gapFragile });
    expect(f.nativeElement.querySelector('sb-chip')).toBeNull();
  });

  it('shows dashes for absent sizing and gap data without an invented percent', () => {
    const f = mount();
    expect(rows(f)).toEqual([
      ['Shares', '—'], ['Deployed', '—'], ['Sizing mode', '—'], ['Working stop', '—'], ['Gap risk (p90)', '—'],
    ]);
    expect(f.nativeElement.textContent).not.toContain('%');
    expect(f.nativeElement.querySelector('sb-chip')).toBeNull();
  });
});
