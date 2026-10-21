import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core'; import { TestBed } from '@angular/core/testing'; import { beforeEach, describe, expect, it } from 'vitest'; import { Waterfall } from './waterfall';
describe('Waterfall', () => { beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] })); it('walks from zero through each step to total', () => { const fixture = TestBed.createComponent(Waterfall); fixture.componentRef.setInput('steps', [{ label: 'MACD', value: 4, n: 40 }, { label: 'RSI', value: -6, n: 30 }, { label: 'Other', value: 1, n: 12 }]); fixture.detectChanges(); const bars = [...(fixture.nativeElement as HTMLElement).querySelectorAll('rect.bar')]; expect(bars.length).toBe(4); expect(bars[0].getAttribute('data-tone')).toBe('pos'); expect(bars[1].getAttribute('data-tone')).toBe('neg'); expect(bars[3].getAttribute('data-tone')).toBe('total'); expect(fixture.componentInstance['runs']()).toEqual([[0, 4], [4, -2], [-2, -1], [0, -1]]); }); });

/* Mirrors waterfall.ts: W = 320 (viewBox width), LABEL_W = 96, VALUE_W = 44. */
const W = 320, LABEL_W = 96, VALUE_W = 44;

describe('Waterfall containment (v179 §3.3)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function render(steps: { label: string; value: number }[]) {
    const fixture = TestBed.createComponent(Waterfall);
    fixture.componentRef.setInput('steps', steps);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('keeps every value label inside the viewBox, on both sides of zero', () => {
    const el = render([
      { label: 'MACD', value: 40 }, { label: 'RSI', value: -55 }, { label: 'Bollinger', value: 30 },
    ]);
    for (const text of el.querySelectorAll<SVGTextElement>('text.value')) {
      const x = Number(text.getAttribute('x'));
      if (text.getAttribute('text-anchor') === 'start') expect(x + VALUE_W).toBeLessThanOrEqual(W);
      else expect(x - VALUE_W).toBeGreaterThanOrEqual(LABEL_W);
    }
  });

  it('shortens a long label to fit its column and keeps the full name as a title', () => {
    const el = render([{ label: 'Support bounce with volume confirmation', value: 2 }]);
    const label = el.querySelector('text.label')!;
    expect(label.firstChild!.textContent!.trim()).toBe('Support bounc…');
    expect(label.querySelector('title')!.textContent).toBe('Support bounce with volume confirmation');
  });

  it('clips at its own box instead of painting past it', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/ui/waterfall.ts'), 'utf8');
    expect(src).toContain('svg { display:block; overflow:hidden; }');
    expect(src).toContain(':host { display:block; min-width:0; }');
  });
});

describe('Waterfall draws at its own width (v179 layout audit: 11px text stays 11px)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('sets the viewBox to the host box width, so one unit is one pixel and the labels never shrink', async () => {
    const original = Object.getOwnPropertyDescriptor(Element.prototype, 'clientWidth')!;
    Object.defineProperty(Element.prototype, 'clientWidth', {
      configurable: true, get() { return (this as HTMLElement).classList.contains('host') ? 291 : 0; },
    });
    try {
      const fixture = TestBed.createComponent(Waterfall);
      fixture.componentRef.setInput('steps', [{ label: 'MACD', value: 4 }]);
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).querySelector('svg')!.getAttribute('viewBox')).toMatch(/^0 0 291 /);
    } finally {
      Object.defineProperty(Element.prototype, 'clientWidth', original);
    }
  });

  it('sizes its labels and values from the 11px token, not a literal', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/ui/waterfall.ts'), 'utf8');
    expect(src).not.toMatch(/font-size:\s*11px/);
    expect(src).toMatch(/\.label \{[^;]*;\s*font-size:\s*var\(--text-micro\)/);
    expect(src).toMatch(/\.value \{[^}]*font-size:\s*var\(--text-micro\)/);
  });
});
