import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ChartContainer } from './chart-container';
import { QualityChip, qualityTone } from './chip';
import { MetricChip } from './metric-chip';
import { Sparkline, sparklinePath } from './sparkline';
import { StatusIndicator, slToTpProgress } from './status-indicator';

/* NG40 — the display components. Colour rules updated by SR2 (spec v18).
 *
 * The colour rules are still the point of most of these assertions, but the
 * rule itself changed. Spec v20 made green and red mean P&L direction and
 * nothing else, so a quality chip had to be greyscale — green for "high
 * confidence" beside green for "in profit" made both meaningless.
 *
 * Spec v18 replaces that with *one colour, one valence*: green means good in
 * every domain, red means bad in every domain. A high-confidence chip and a
 * profitable cell are then both saying "good", which is coherent rather than
 * ambiguous. So these tests still check which class is applied — that has not
 * changed — but the band a value earns is no longer constrained to grey.
 */

describe('qualityTone', () => {
  it('maps a confidence level straight onto its band', () => {
    expect(qualityTone(1)).toBe('q1');
    expect(qualityTone(2)).toBe('q2');
    expect(qualityTone(3)).toBe('q3');
    expect(qualityTone(4)).toBe('q4');
    expect(qualityTone(5)).toBe('q5');
  });

  it('folds the three-step tier scale onto the five-step ramp', () => {
    // C is amber rather than red: a weak tier is a caution, not a loss.
    expect(qualityTone('A')).toBe('q5');
    expect(qualityTone('B')).toBe('q3');
    expect(qualityTone('C')).toBe('q2');
  });

  it('treats an unrated value as neutral rather than as the worst band', () => {
    expect(qualityTone(null)).toBe('neutral');
    expect(qualityTone(undefined)).toBe('neutral');
    expect(qualityTone('')).toBe('neutral');
    expect(qualityTone('unrated')).toBe('neutral');
  });

  it('treats a level outside 1-5 as neutral, not as a token that does not exist', () => {
    // `q9` would render as var(--quality-9) -> nothing -> invisible text.
    expect(qualityTone(0)).toBe('neutral');
    expect(qualityTone(9)).toBe('neutral');
    expect(qualityTone(Number.NaN)).toBe('neutral');
  });

  it('is case- and whitespace-insensitive about tiers', () => {
    expect(qualityTone(' b ')).toBe('q3');
  });
});

describe('slToTpProgress', () => {
  it('runs 0 at the stop to 1 at the target', () => {
    expect(slToTpProgress(100, 100, 120)).toBe(0);
    expect(slToTpProgress(110, 100, 120)).toBeCloseTo(0.5);
    expect(slToTpProgress(120, 100, 120)).toBe(1);
  });

  it('handles a short without a branch', () => {
    // target < stop, so both halves of the ratio flip sign.
    expect(slToTpProgress(90, 100, 80)).toBeCloseTo(0.5);
    expect(slToTpProgress(80, 100, 80)).toBe(1);
  });

  it('clamps rather than running past either end', () => {
    expect(slToTpProgress(130, 100, 120)).toBe(1);
    expect(slToTpProgress(90, 100, 120)).toBe(0);
  });

  it('is null, not zero, when it cannot be known', () => {
    // Zero means "sitting on the stop", the worst a live trade can be.
    // Showing that for a trade with no quote would be a lie in the
    // frightening direction.
    expect(slToTpProgress(null, 100, 120)).toBeNull();
    expect(slToTpProgress(110, null, 120)).toBeNull();
    expect(slToTpProgress(110, 100, null)).toBeNull();
  });

  it('is null when the stop and target are the same price', () => {
    expect(slToTpProgress(110, 100, 100)).toBeNull();
  });
});

describe('sparklinePath', () => {
  it('is empty for no points', () => {
    expect(sparklinePath([])).toBe('');
  });

  it('draws a single point as a flat line rather than as nothing', () => {
    // One data point rendering as nothing is indistinguishable from having
    // no data at all.
    expect(sparklinePath([5])).toMatch(/^M 0 .+ L 100 /);
  });

  it('draws a flat series down the middle', () => {
    // Not at the top or the bottom, where a flat line reads as an extreme.
    expect(sparklinePath([7, 7, 7])).toContain('12.00');
  });

  it('spans the full width and puts the low below the high', () => {
    const path = sparklinePath([1, 2, 3]);
    const ys = [...path.matchAll(/[ML] [\d.]+ ([\d.]+)/g)].map((m) => Number(m[1]));

    expect(path.startsWith('M 0.00 ')).toBe(true);
    expect(path).toContain('L 100.00');
    // SVG y grows downward, so the largest value has the smallest y.
    expect(ys[0]).toBeGreaterThan(ys[2]);
  });
});

@Component({
  imports: [StatusIndicator, QualityChip, Sparkline, MetricChip, ChartContainer],
  template: `
    <sb-status-indicator
      [status]="status()"
      [current]="current()"
      [entry]="100"
      [stop]="90"
      [target]="120"
    />
    <sb-quality-chip [value]="quality()" label="Lv" />
    <sb-sparkline [points]="points()" />
    <sb-metric-chip label="Win rate" [value]="metric()" tone="pnl" unit="%" />
    <sb-chart-container [loading]="loading()" [error]="error()" [hasData]="hasData()" />
  `,
})
class Host {
  readonly status = signal('open');
  readonly current = signal<number | null>(110);
  readonly quality = signal<number | string | null>(5);
  readonly points = signal<number[]>([1, 2, 3]);
  readonly metric = signal<number | null>(4);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly hasData = signal(true);
}

describe('display components', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  const el = (): HTMLElement => fixture.nativeElement;
  const dot = () => el().querySelector('.dot')!;

  it('colours the status dot green or red only for a settled outcome', () => {
    // An open trade shown in green would claim a profit it has not made.
    expect(dot().className).toContain('open');
    expect(dot().className).not.toContain('win');

    host.status.set('win');
    fixture.detectChanges();
    expect(dot().className).toContain('win');

    host.status.set('loss');
    fixture.detectChanges();
    expect(dot().className).toContain('loss');
  });

  it('greys out a cancelled or expired plan rather than colouring it', () => {
    host.status.set('cancelled');
    fixture.detectChanges();
    expect(dot().className).toContain('inert');
  });

  it('shows the SL→TP bar only while the trade is open', () => {
    expect(el().querySelector('[role=progressbar]')).not.toBeNull();

    host.status.set('win');
    fixture.detectChanges();
    // On a closed trade the bar is a frozen snapshot of a position that no
    // longer exists.
    expect(el().querySelector('[role=progressbar]')).toBeNull();
  });

  it('reports the bar position to assistive technology', () => {
    expect(el().querySelector('[role=progressbar]')!.getAttribute('aria-valuenow')).toBe('67');
  });

  it('colours the bar fill by price against the entry', () => {
    expect(el().querySelector('.fill')!.className).toContain('pos');

    host.current.set(95);
    fixture.detectChanges();
    expect(el().querySelector('.fill')!.className).toContain('neg');
  });

  it('hides the bar when there is no price to place on it', () => {
    host.current.set(null);
    fixture.detectChanges();
    expect(el().querySelector('[role=progressbar]')).toBeNull();
  });

  it('renders a quality chip on the band its value earns', () => {
    expect(el().querySelector('.chip')!.className).toContain('q5');

    host.quality.set('C');
    fixture.detectChanges();
    expect(el().querySelector('.chip')!.className).toContain('q2');
  });

  it('colours a sparkline by its net direction', () => {
    expect(el().querySelector('sb-sparkline path')!.getAttribute('class')).toBe('pos');

    host.points.set([3, 1, 2, 0]);
    fixture.detectChanges();
    expect(el().querySelector('sb-sparkline path')!.getAttribute('class')).toBe('neg');
  });

  it('draws no sparkline at all for an empty series', () => {
    host.points.set([]);
    fixture.detectChanges();
    expect(el().querySelector('sb-sparkline svg')).toBeNull();
  });

  it('renders a null metric as an em dash, not as zero', () => {
    host.metric.set(null);
    fixture.detectChanges();

    const value = el().querySelector('sb-metric-chip .value')!;
    expect(value.textContent!.trim()).toBe('—');
    expect(value.className).toContain('absent');
  });

  it('keeps the chart surface mounted in every state', () => {
    // A chart library that measures an element which appears a tick later
    // measures zero and renders nothing.
    host.loading.set(true);
    fixture.detectChanges();
    expect(el().querySelector('.surface')).not.toBeNull();
    expect(el().querySelector('.surface')!.className).toContain('hidden');
    expect(el().querySelector('.spinner')).not.toBeNull();
  });

  it('prefers the chart error over the spinner', () => {
    // A refetch that failed should say so rather than spin forever.
    host.loading.set(true);
    host.error.set('Price data is unavailable');
    fixture.detectChanges();

    expect(el().querySelector('.spinner')).toBeNull();
    expect(el().textContent).toContain('Price data is unavailable');
  });

  it('distinguishes no bars from an error', () => {
    host.hasData.set(false);
    fixture.detectChanges();

    expect(el().textContent).toContain('No price history');
  });
});
