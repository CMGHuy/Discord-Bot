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

  it('marks a good or bad figure on its host and colours the figure', () => {
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

  it('keeps the judgement on the host and the value, and never fills the card (v195 Phase 2)', () => {
    expect(SOURCE).not.toMatch(/:host\(\.tint-(pos|neg)\) \.card/);
    expect(SOURCE).not.toContain('--tile-tint-off');
    expect(SOURCE).not.toContain('linear-gradient');
    const good = render({ value: 1.2, tint: 'pos' });
    expect(good.classList).toContain('tint-pos');
    expect(good.querySelector('.value')!.classList).toContain('pos');
    const bad = render({ value: -0.4, tint: 'neg' });
    expect(bad.classList).toContain('tint-neg');
    expect(bad.querySelector('.value')!.classList).toContain('neg');
  });

  it('pads and spaces like a stat tile, following row density (v195 Phase 2)', () => {
    const card = rule('.card');
    expect(card).toContain('gap: var(--space-4);');
    expect(card).toContain('padding: var(--space-10) var(--panel-pad);');
    expect(card).not.toContain('var(--space-20)');
    expect(rule('.busy')).toContain('right: var(--panel-pad);');
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

describe('sb-metric-card figure face (v186 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/metric-card.ts'), 'utf8');
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  /** The rule whose selector starts a line, so `.value` is not `:host(.loading) .value`. */
  const rule = (selector: string) =>
    SOURCE.match(new RegExp(`\\n\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('sets the value in the figure face at weight 600, not 700', () => {
    const value = rule('.value');
    expect(value).toContain('font-family: var(--font-figure);');
    expect(value).toContain('font-weight: var(--figure-weight);');
    expect(value).toContain('letter-spacing: var(--figure-tracking);');
    expect(value).toContain('font-variant-numeric: tabular-nums;');
    expect(value).not.toContain('font-weight: 700');
    // The density register still sizes the figure.
    expect(value).toContain('font-size: var(--register-figure, var(--text-metric));');
  });

  it('drops the global num class from the value and keeps it on the sub line', () => {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Expectancy');
    f.componentRef.setInput('value', 0.42);
    f.componentRef.setInput('sub', 'N=31');
    f.detectChanges();
    const host = f.nativeElement as HTMLElement;
    expect(host.querySelector('.value')!.classList).not.toContain('num');
    expect(host.querySelector('.sub')!.classList).toContain('num');
  });
});

describe('sb-metric-card loading and tooltip', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(MetricCard);
    f.componentRef.setInput('label', 'Win rate');
    f.componentRef.setInput('value', 55);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return { f, host: f.nativeElement as HTMLElement };
  }

  it('shows no ring and is not busy by default', () => {
    const { host } = mount({});
    expect(host.querySelector('sb-spinner')).toBeNull();
    expect(host.classList.contains('loading')).toBe(false);
    expect(host.getAttribute('aria-busy')).toBeNull();
  });

  it('shows a ring inside the card, keeps the figure and marks the card busy while loading', () => {
    const { host } = mount({ loading: true });
    expect(host.querySelector('.card sb-spinner')).not.toBeNull();
    expect(host.classList.contains('loading')).toBe(true);
    expect(host.getAttribute('aria-busy')).toBe('true');
    expect(host.querySelector('.value')).not.toBeNull();
  });

  it('drops the ring again when the refetch lands', () => {
    const { f, host } = mount({ loading: true });
    f.componentRef.setInput('loading', false);
    f.detectChanges();
    expect(host.querySelector('sb-spinner')).toBeNull();
    expect(host.getAttribute('aria-busy')).toBeNull();
  });

  it('explains itself through a hint beside its label when given a description', () => {
    const { host } = mount({ description: 'The share of closed trades that won.' });
    expect(host.hasAttribute('title')).toBe(false);
    const hint = host.querySelector('.label-row sb-hint')!;
    expect(hint.querySelector('[role="tooltip"]')!.textContent!.trim()).toBe('The share of closed trades that won.');
    expect(hint.querySelector('button')!.getAttribute('aria-label')).toMatch(/^About /);
    expect(host.querySelector('.label')!.textContent).not.toContain('The share of closed trades');
  });

  it('has no tooltip and no hint without a description', () => {
    const { host } = mount({});
    expect(host.hasAttribute('title')).toBe(false);
    expect(host.querySelector('sb-hint')).toBeNull();
  });
});
