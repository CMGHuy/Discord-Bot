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

  it('says "trailing", not "no price", for a runner with no target', () => {
    const el = render({
      ...live, status: 'PARTIAL', progress_pct: null, progress_band: null,
      blink_seconds: null, bar_kind: 'trailing',
    });
    expect(el.querySelector('.fill')).toBeNull();
    expect(el.textContent).toContain('PARTIAL');
    expect(el.textContent).toContain('trailing');
    expect(el.textContent).not.toContain('no price');
  });

  it('draws the bar with P&L at both ends and no icon (the icon lives in the ID cell)', () => {
    const el = render({ ...live, status: 'PARTIAL', bar_kind: 'trailing', banked_fraction: 0.5,
      stop_pnl_pct: 1.25, best_pnl_pct: 6 });
    expect(el.querySelector('.fill')).not.toBeNull();
    expect(el.querySelectorAll('sb-icon').length).toBe(0);
    expect(el.querySelector('.end.neg')!.textContent).toBe('+1.3%');
    expect(el.querySelector('.end.pos')!.textContent).toBe('+6.0%');
  });

  it('adds no icons to an ordinary PARTIAL row with a TP2 bar', () => {
    const el = render({ ...live, status: 'PARTIAL', bar_kind: 'progress', banked_fraction: 0.5 });
    expect(el.querySelectorAll('sb-icon').length).toBe(0);
  });

  it('says how much of a trailing runner is still open', () => {
    const el = render({
      ...live, status: 'PARTIAL', progress_pct: null, progress_band: null,
      blink_seconds: null, bar_kind: 'trailing', banked_fraction: 0.5,
    });
    expect(el.textContent).toContain('50% open');
    expect(el.textContent).toContain('trailing');
  });

  it('shows the open share for a PARTIAL runner that still has a bar', () => {
    const el = render({ ...live, status: 'PARTIAL', banked_fraction: 0.4 });
    expect(el.textContent).toContain('60% open');
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

  // -- current_price_stale (2026-09-18, the MRNA incident) ------------------
  // A fast_info fallback echoed yesterday's close during premarket and the
  // bar read "Near stop-loss" for a position that never touched it. The bar
  // still draws at its real, computed position -- this only adds a visible
  // "the number behind this might be delayed" flag beside it.

  it('shows a delayed flag on a live bar built from a stale price', () => {
    const el = render({ ...live, current_price_stale: true });
    expect(el.textContent).toContain('delayed');
  });

  it('shows no delayed flag on a live bar built from a fresh price', () => {
    const el = render({ ...live, current_price_stale: false });
    expect(el.querySelector('.stale')).toBeNull();
  });
});
