import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Realized } from '../../../stores/dashboard.store';
import { PANEL_HELP } from './panel-help';
import { RealizedPnl } from './realized-pnl';
import { ScopePreset, ScopeSelection, rangeChipLabel } from './equity-range.model';

const TODAY: Realized = { amount: 12.5, pct: 0.4, n: 2, wins: 1, losses: 1 };
const SCOPED: Realized = { amount: -480, pct: -3.1, n: 18, wins: 7, losses: 11 };
const NONE: Realized = { amount: null, pct: null, n: 0, wins: 0, losses: 0 };
const preset = (value: ScopePreset): ScopeSelection => ({ kind: 'preset', preset: value });
const WINDOW = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };

describe('sb-realized-pnl', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(RealizedPnl);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    return {
      f, el,
      amount: () => el.querySelector('.amount')!.textContent!.trim(),
      pct: () => el.querySelector('.pct')!.textContent!.trim(),
      window: () => el.querySelector('.window')!.textContent!.trim(),
      stats: () => [...el.querySelectorAll('.stats dd')].map((d) => d.textContent!.trim()),
      segments: () => [...el.querySelectorAll('.segment')].map((b) => b.textContent!.trim()),
      segment: (label: string) => [...el.querySelectorAll<HTMLButtonElement>('.segment')]
        .find((b) => b.textContent!.trim() === label)!,
      choose(label: string) {
        this.segment(label).click();
        f.detectChanges();
      },
    };
  }

  it('shows today as the default, with no choice to make, while the scope is 1D', () => {
    const view = mount({ scope: TODAY, today: TODAY, selection: preset('1D'), currency: '€' });
    expect(view.amount()).toBe('+12.50 €');
    expect(view.pct()).toBe('+0.40%');
    expect(view.window()).toBe('Today');
    expect(view.stats()).toEqual(['2', '1', '1']);
    expect(view.el.querySelector('sb-segmented')).toBeNull();
  });

  it('follows the scope the chart sets: a preset, or the range it was dragged to', () => {
    const month = mount({ scope: SCOPED, today: TODAY, selection: preset('1M'), currency: '€' });
    expect(month.amount()).toContain('480.00');
    expect(month.pct()).toBe('-3.10%');
    expect(month.window()).toBe('1M');
    const range = mount({ scope: SCOPED, today: TODAY, selection: { kind: 'range', window: WINDOW }, currency: '€' });
    expect(range.window()).toBe(`Range ${rangeChipLabel(WINDOW)}`);
    expect(mount({ scope: SCOPED, today: TODAY, selection: preset('All'), currency: '€' }).window()).toBe('All days');
  });

  it('offers Today beside the scope when the scope is wider, and switches without touching the scope', () => {
    const view = mount({ scope: SCOPED, today: TODAY, selection: preset('YTD'), currency: '€' });
    expect(view.segments()).toEqual(['YTD', 'Today']);
    expect(view.segment('YTD').getAttribute('aria-pressed')).toBe('true');
    view.choose('Today');
    expect(view.amount()).toBe('+12.50 €');
    expect(view.window()).toBe('Today');
    expect(view.stats()).toEqual(['2', '1', '1']);
    view.choose('YTD');
    expect(view.amount()).toContain('480.00');
  });

  it('labels the first choice Range under a hand-picked range', () => {
    const view = mount({ scope: SCOPED, today: TODAY, selection: { kind: 'range', window: WINDOW }, currency: '€' });
    expect(view.segments()).toEqual(['Range', 'Today']);
  });

  it('colours the figure by its sign, and leaves zero and nothing plain', () => {
    const tone = (realized: Realized | null) =>
      mount({ scope: realized, today: realized, selection: preset('1D'), currency: '€' })
        .el.querySelector('.amount')!.getAttribute('data-tone');
    expect(tone(TODAY)).toBe('pos');
    expect(tone(SCOPED)).toBe('neg');
    expect(tone({ ...TODAY, amount: 0 })).toBe('neutral');
    expect(tone(NONE)).toBe('neutral');
    expect(tone(null)).toBe('neutral');
  });

  it('shows dashes, never zeros, before the first response', () => {
    const view = mount({ selection: preset('1D'), currency: '€' });
    expect(view.amount()).toBe('—');
    expect(view.pct()).toBe('—');
    expect(view.stats()).toEqual(['—', '—', '—']);
    expect(view.el.querySelector('.hint')).toBeNull();
  });

  it('says why nothing is shown when nothing closed, in the window own words', () => {
    const hint = (selection: ScopeSelection, choose?: string) => {
      const view = mount({ scope: NONE, today: NONE, selection, currency: '€' });
      if (choose) view.choose(choose);
      return view.el.querySelector('.hint')?.textContent?.trim() ?? null;
    };
    expect(hint(preset('1D'))).toBe('none closed today');
    expect(hint(preset('1M'))).toBe('none closed in range');
    expect(hint(preset('1M'), 'Today')).toBe('none closed today');
    expect(hint(preset('All'))).toBe('none closed');
  });

  it('tolerates a response without the realised block', () => {
    const view = mount({ scope: undefined, today: undefined, selection: preset('1D'), currency: '€' });
    expect(view.amount()).toBe('—');
  });

  describe('loading', () => {
    it('shows a ring inside the figures and keeps the last numbers while the scope refetches', () => {
      const view = mount({ scope: SCOPED, today: TODAY, selection: preset('1M'), currency: '€', loading: true });
      expect(view.el.querySelector('.figures sb-spinner')).not.toBeNull();
      expect(view.el.querySelector('.figures')!.classList.contains('busy')).toBe(true);
      expect(view.el.querySelector('.pnl-body')!.getAttribute('aria-busy')).toBe('true');
      expect(view.amount()).toContain('480.00');
    });

    it('shows no ring when idle', () => {
      const view = mount({ scope: SCOPED, today: TODAY, selection: preset('1M'), currency: '€' });
      expect(view.el.querySelector('sb-spinner')).toBeNull();
      expect(view.el.querySelector('.pnl-body')!.getAttribute('aria-busy')).toBeNull();
    });

    it('rings the Today view only for the today fetch, and the scope view only for the scope fetch', () => {
      const view = mount({ scope: SCOPED, today: TODAY, selection: preset('1M'), currency: '€', loading: true });
      view.choose('Today');
      expect(view.el.querySelector('sb-spinner')).toBeNull();
      view.f.componentRef.setInput('todayLoading', true);
      view.f.detectChanges();
      expect(view.el.querySelector('sb-spinner')).not.toBeNull();
      view.choose('1M');
      view.f.componentRef.setInput('todayLoading', false);
      view.f.detectChanges();
      expect(view.el.querySelector('sb-spinner')).not.toBeNull();
    });

    it('rings under 1D from the scoped fetch, since there the scope is today', () => {
      const view = mount({ scope: TODAY, selection: preset('1D'), currency: '€', loading: true });
      expect(view.el.querySelector('sb-spinner')).not.toBeNull();
    });
  });

  it('dims the figures when the last refetch failed', () => {
    const view = mount({ scope: SCOPED, selection: preset('1M'), currency: '€', stale: true });
    expect(view.el.querySelector('.pnl-body')!.classList.contains('stale')).toBe(true);
  });

  it('explains itself on hover', () => {
    const view = mount({ selection: preset('1D'), currency: '€' });
    expect(view.el.querySelector('sb-panel')!.getAttribute('title')).toBe(PANEL_HELP.realizedPnl);
  });
});
