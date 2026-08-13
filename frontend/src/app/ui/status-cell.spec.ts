import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { StatusCell } from './status-cell';

const live = {
  status: 'ACTIVE',
  progress_pct: 62,
  entry_pct: 40,
  progress_band: 'toward_target',
  blink_seconds: 1.4,
  status_label: 'Trending toward target',
};

function render(row: Record<string, unknown>) {
  const f = TestBed.createComponent(StatusCell);
  f.componentRef.setInput('row', row);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('StatusCell', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders dot, bar and percentage for a live position', () => {
    const el = render(live);
    expect(el.querySelector('.dot')).toBeTruthy();
    expect(el.querySelector('.fill')!.getAttribute('style')).toContain('62%');
    expect(el.querySelector('.tick')!.getAttribute('style')).toContain('40%');
    expect(el.textContent).toContain('62%');
  });

  it('drives the pulse period from blink_seconds', () => {
    expect(render(live).querySelector('.dot')!.getAttribute('style')).toContain('1.4s');
  });

  it('falls back to the status chip when there is no live price', () => {
    const el = render({ ...live, progress_pct: null, progress_band: null, blink_seconds: null });
    expect(el.querySelector('.fill')).toBeNull();
    expect(el.textContent).toContain('no price');
  });

  it('shows the chip alone for a trade that has not opened', () => {
    const el = render({ ...live, status: 'PENDING', progress_pct: null, progress_band: null });
    expect(el.querySelector('.fill')).toBeNull();
    expect(el.textContent).toContain('PENDING');
  });

  it('clamps a price beyond the target to a full bar', () => {
    expect(render({ ...live, progress_pct: 100 }).querySelector('.fill')!.getAttribute('style'))
      .toContain('100%');
  });

  it('exposes the bar to assistive tech as a progressbar', () => {
    // The bar is the whole point of the cell; a div with a width is invisible
    // to anyone not looking at it.
    const bar = render(live).querySelector('[role=progressbar]')!;
    expect(bar.getAttribute('aria-valuenow')).toBe('62');
    expect(bar.getAttribute('aria-label')).toContain('Trending toward target');
  });
});
