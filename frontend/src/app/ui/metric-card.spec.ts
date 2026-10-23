import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { MetricCard } from './metric-card';

describe('sb-metric-card tint (v181 §5)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Figure');
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    const host = f.nativeElement as HTMLElement;
    return { host, value: host.querySelector('.value')! };
  }

  it('tints the card and colours the figure for a good or bad figure', () => {
    const good = render({ value: 1.2, tint: 'pos' });
    expect(good.host.classList.contains('tint-pos')).toBe(true);
    expect(good.value.classList.contains('pos')).toBe(true);
    const bad = render({ value: 1.2, tint: 'neg' });
    expect(bad.host.classList.contains('tint-neg')).toBe(true);
    expect(bad.value.classList.contains('neg')).toBe(true);
  });

  it('colours a warning figure without tinting the card', () => {
    const { host, value } = render({ value: 5, tint: 'warn' });
    expect(value.classList.contains('warn')).toBe(true);
    expect(host.classList.contains('tint-pos') || host.classList.contains('tint-neg')).toBe(false);
  });

  it('leaves a neutral card plain, whatever the sign', () => {
    const { host, value } = render({ value: -3, tint: 'neutral', tone: 'pnl' });
    expect(['pos', 'neg', 'warn'].some((c) => value.classList.contains(c))).toBe(false);
    expect(host.classList.contains('tint-neg')).toBe(false);
  });

  it('never colours or tints the dash of a missing figure', () => {
    const { host, value } = render({ value: null, tint: 'pos' });
    expect(value.classList.contains('absent')).toBe(true);
    expect(value.classList.contains('pos')).toBe(false);
    expect(host.classList.contains('tint-pos')).toBe(false);
  });

  it('keeps the v80 tone rule when no tint is given', () => {
    const { host, value } = render({ value: -2, tone: 'pnl' });
    expect(value.classList.contains('neg')).toBe(true);
    expect(host.classList.contains('tint-neg')).toBe(false);
  });
});

describe('sb-metric-card in and out of a strip (v186 D3)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/metric-card.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  /** The rule whose selector starts a line, so `.card` is not `:host(.tint-pos) .card`. */
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`(?:^|\\n)\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Figure');
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('draws the strip hairline on its host, start edges only, inside its cell', () => {
    const host = rule(':host');
    expect(host).toContain('box-sizing: border-box;');
    expect(host).toContain('border-left: var(--figure-rule, 0px) solid var(--border);');
    expect(host).toContain('border-top: var(--figure-rule, 0px) solid var(--border);');
    expect(SOURCE).not.toMatch(/border-(right|bottom):\s*var\(--figure-rule/);
  });

  it("reads its surface, frame and corner from a strip, defaulting to today's", () => {
    const card = rule('.card');
    expect(card).toContain('background: var(--tile-bg, var(--surface));');
    expect(card).toContain('border: var(--tile-border, 1px solid var(--border));');
    expect(card).toContain('border-radius: var(--tile-radius, var(--panel-radius));');
  });

  it('drops its tint where a strip switches it off, keeps it everywhere else', () => {
    expect(rule(':host(.tint-pos) .card')).toContain(
      'background: var(--tile-tint-off, linear-gradient(var(--pos-soft), var(--pos-soft)), var(--surface));',
    );
    expect(rule(':host(.tint-neg) .card')).toContain(
      'background: var(--tile-tint-off, linear-gradient(var(--neg-soft), var(--neg-soft)), var(--surface));',
    );
    // The judgement itself stays on the host and the value: only the fill is switchable.
    const host = render({ value: 1.2, tint: 'pos' });
    expect(host.classList).toContain('tint-pos');
    expect(host.querySelector('.value')!.classList).toContain('pos');
  });

  it('labels in the shared field-label style, with no typography of its own', () => {
    expect(render({ value: 1 }).querySelector('.label')!.classList).toContain('sb-label');
    expect(SOURCE).not.toMatch(/(?:^|\n)\s*\.label\s*\{/);
  });

  it('shows the dash of a missing figure in a readable colour', () => {
    expect(rule('.absent')).toContain('color: var(--text-muted);');
    expect(SOURCE).not.toMatch(/color:\s*var\(--text-faint\)/);
    expect(render({ value: null }).querySelector('.value')!.classList).toContain('absent');
  });
});
