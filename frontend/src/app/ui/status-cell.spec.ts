import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { NO_PRICE_REASON } from './position-format';
import { PREV_CLOSE_LABEL } from './position-progress';
import { PERFORMANCE_CAVEAT } from './stat-tile';
import { STATUS_ENDS_HINT, STATUS_STALE_HINT, StatusCell, partialOpenTitle } from './status-cell';

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

  const TRAILING = { ...live, status: 'PARTIAL', bar_kind: 'trailing', banked_fraction: 0.5,
    stop_pnl_pct: 1.25, best_pnl_pct: 6 };

  it('draws the bar with P&L at both ends and no icon (the icon lives in the ID cell)', () => {
    const el = render(TRAILING);
    expect(el.querySelector('.fill')).not.toBeNull();
    expect([...el.querySelectorAll('sb-icon')].filter((i) => !i.closest('sb-hint')).length).toBe(0);
    expect(el.querySelector('.end.neg')!.textContent).toBe('+1.3%');
    expect(el.querySelector('.end.pos')!.textContent).toBe('+6.0%');
  });

  it('signs a negative trailing stop and best P&L with the true minus; zero and positive unchanged', () => {
    const neg = render({ ...TRAILING, stop_pnl_pct: -2.34, best_pnl_pct: -0.04 });
    expect(neg.querySelector('.end.neg')!.textContent).toBe('−2.3%');
    // v240 Decision 10: a best P&L of −0.04 rounds to zero at one decimal,
    // so it prints unsigned.
    expect(neg.querySelector('.end.pos')!.textContent).toBe('0.0%');
    expect(neg.querySelector('.end.neg')!.textContent).not.toContain('-');
    const zero = render({ ...TRAILING, stop_pnl_pct: 0, best_pnl_pct: 6 });
    expect(zero.querySelector('.end.neg')!.textContent).toBe('0.0%');
  });

  it('adds no icons to an ordinary PARTIAL row with a TP2 bar', () => {
    const el = render({ ...live, status: 'PARTIAL', bar_kind: 'progress', banked_fraction: 0.5 });
    expect([...el.querySelectorAll('sb-icon')].filter((i) => !i.closest('sb-hint')).length).toBe(0);
  });

  it('says how much of a trailing runner is still open', () => {
    const el = render({
      ...live, status: 'PARTIAL', progress_pct: null, progress_band: null,
      blink_seconds: null, bar_kind: 'trailing', banked_fraction: 0.5,
    });
    expect(el.textContent).not.toContain('open');
    expect(el.textContent).toContain('trailing');
  });

  it('shows the open share for a PARTIAL runner that still has a bar', () => {
    const el = render({ ...live, status: 'PARTIAL', banked_fraction: 0.4 });
    expect(el.textContent).not.toContain('open');
  });

  it('puts the open share in the partial icon tooltip instead', () => {
    expect(partialOpenTitle({ status: 'PARTIAL', banked_fraction: 0.5 })).toBe('Partially closed -- 50% still open');
    expect(partialOpenTitle({ status: 'ACTIVE', banked_fraction: null })).toBeNull();
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

  it('explains the two trailing P&L ends in one hint, not two titles (v194 A3)', () => {
    const el = render(TRAILING);
    expect(el.querySelector('.end[title]')).toBeNull();
    expect(el.querySelector('sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(STATUS_ENDS_HINT);
  });

  it('explains a delayed price in a hint beside the word', () => {
    const el = render({ ...live, current_price_stale: true });
    expect(el.querySelector('.stale')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.stale')!.textContent!.trim()).toBe('delayed');
    expect(el.querySelector('.stale + sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(STATUS_STALE_HINT);
  });
});

describe('status cell on one baseline (v179 layout audit)', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/status-cell.ts'), 'utf8');

  it('sets the percentage and the hint on the text baseline, the textless bar centred', () => {
    expect(src.match(/\.cell \{[^}]*\}/)![0]).toMatch(/align-items:\s*baseline/);
    expect(src).toMatch(/\.track \{[^}]*align-self:\s*center/);
  });

  it('wraps only the no-bar cell (hint + reason): the bar cell keeps dot, track and percentage on one line', () => {
    expect(src.match(/\.cell \{[^}]*\}/)![0]).not.toMatch(/flex-wrap/);
    expect(src).toMatch(/\.cell\.no-bar \{[^}]*flex-wrap:\s*wrap/);
  });
});

describe('STATUS_ENDS_HINT copy (A4 audit)', () => {
  it('says the two ends are percent of the entry price, on the paper, gross, pre-tax basis', () => {
    expect(STATUS_ENDS_HINT).toContain('per share from the original entry');
    expect(STATUS_ENDS_HINT).toContain(PERFORMANCE_CAVEAT);
  });
});

describe('partialOpenTitle on a closed later leg', () => {
  it('has no title: the leg label, not an icon, marks a closed leg (v194 B3)', () => {
    expect(partialOpenTitle({ status: 'CLOSED', banked_fraction: null })).toBeNull();
  });
});

describe('StatusCell v248', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('a prev-close bar is neutral, still, and titled as not live, whatever band arrives', () => {
    const el = render({ ...live, price_kind: 'prev_close', current_price: 92, progress_pct: 0,
      progress_band: 'toward_stop', blink_seconds: 0.5, status_label: 'Near stop-loss' });
    expect(el.querySelector('.fill')!.classList).toContain('neutral');
    expect(el.querySelector('.fill')!.classList).not.toContain('toward_stop');
    expect(el.querySelector('.dot')!.hasAttribute('data-still')).toBe(true);
    expect(el.querySelector('.track')!.getAttribute('title')).toBe(PREV_CLOSE_LABEL);
    expect(el.querySelector('.track')!.getAttribute('aria-label')).toBe(PREV_CLOSE_LABEL);
  });
  it('a live bar keeps its band, pulse and label', () => {
    const el = render({ ...live, price_kind: 'live', current_price: 110 });
    expect(el.querySelector('.fill')!.classList).toContain('toward_target');
    expect(el.querySelector('.dot')!.hasAttribute('data-still')).toBe(false);
    expect(el.querySelector('.track')!.getAttribute('title')).toBe('Trending toward target');
  });
  const unpriced = { ...live, progress_pct: null, progress_band: null, blink_seconds: null, status_label: 'No live price' };
  it('a held row with neither price nor close says "no price yet" and why', () => {
    for (const status of ['ACTIVE', 'PARTIAL']) {
      const el = render({ ...unpriced, status, current_price: null, last_close: null });
      expect(el.querySelector('.hint')!.textContent!.trim()).toBe('no price yet');
      expect(el.querySelector('.reason')!.textContent!.trim()).toBe(NO_PRICE_REASON);
    }
  });
  it('"no price yet" wins over "trailing" for a runner with no price at all', () => {
    const el = render({ ...unpriced, status: 'PARTIAL', bar_kind: 'trailing', current_price: null, last_close: null });
    expect(el.querySelector('.hint')!.textContent!.trim()).toBe('no price yet');
  });
  it('a held row with a cached close, or with no current_price field, keeps "no price"', () => {
    expect(render({ ...unpriced, current_price: null, last_close: 36.86 }).querySelector('.hint')!.textContent!.trim()).toBe('no price');
    expect(render(unpriced).querySelector('.hint')!.textContent!.trim()).toBe('no price');
    expect(render(unpriced).querySelector('.reason')).toBeNull();
  });
  it('a PENDING row with no price stays a bare chip', () => {
    expect(render({ ...unpriced, status: 'PENDING', current_price: null, last_close: null }).querySelector('.hint')).toBeNull();
  });
});
