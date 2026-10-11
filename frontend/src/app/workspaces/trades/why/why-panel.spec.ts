import { Component, computed, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { GateRow } from '../../../api/models';
import { GATE_CAVEAT, WHY_SECTIONS, WhyPanel, WhySection, marginTone } from './why-panel';

@Component({
  imports: [WhyPanel],
  template: `<sb-why-panel [sections]="sections()" />`,
})
class ReadonlySectionsHost {
  readonly sections = computed<readonly WhySection[]>(() => ['gates']);
}

function mount(inputs: Record<string, unknown> = {}): ComponentFixture<WhyPanel> {
  const fixture = TestBed.createComponent(WhyPanel);
  for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
  return fixture;
}

function gate(over: Partial<GateRow> = {}): GateRow {
  return { key: 'rs', label: 'Relative strength', value: 80, threshold: 70,
    margin: 10, applies: true, parts: [{ label: 'Rank', value: 80 }], note: 'Current rank', ...over };
}

describe('marginTone', () => {
  it.each(['CLOSED', 'CANCELLED', 'EXPIRED', null])('neutralizes terminal or absent status %s', (status) => {
    expect(marginTone(status, 3, 1)).toBe('neutral');
  });
  it('neutralizes pending expiry before checking age', () => {
    expect(marginTone('PENDING', 0, null)).toBe('neutral');
  });
  it.each(['PENDING', 'ACTIVE', 'PARTIAL'])('signs recent %s and marks missing or old age indicative', (status) => {
    expect(marginTone(status, 2, 5)).toBe('signed');
    expect(marginTone(status, 2, 6)).toBe('indicative');
    expect(marginTone(status, 2, null)).toBe('indicative');
  });
  it('keeps active margins signed even at zero pending expiry bars', () => {
    expect(marginTone('ACTIVE', 0, 0)).toBe('signed');
  });
});

describe('WhyPanel', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  it('accepts a readonly computed section list from its host', () => {
    const f = TestBed.createComponent(ReadonlySectionsHost);
    f.detectChanges();
    expect(f.nativeElement.querySelectorAll('sb-panel')).toHaveLength(1);
    expect(f.nativeElement.textContent).toContain("Gate margins (vs today's thresholds)");
  });

  it('renders the five sections in canonical order with quality inside confidence', () => {
    const f = mount({ sections: [...WHY_SECTIONS].reverse(), confidenceFactors: [{ factor: 'Trend', note: 'Up' }],
      qualityFactors: [{ label: 'Structure', points: 2 }], explanation: '**Strong** setup' });
    expect([...f.nativeElement.querySelectorAll('h2')].map((el: HTMLElement) => el.textContent?.trim())).toEqual([
      'Levels & methods', 'Confidence breakdown', "Gate margins (vs today's thresholds)",
      'Calendar in the holding window', 'Why this trade',
    ]);
    expect(f.nativeElement.textContent).toContain('Quality breakdown');
    expect(f.nativeElement.querySelector('sb-inline-md b').textContent).toBe('Strong');
  });

  it('shows trigger fallback, optional acceptance, source labels and strategy horizons', () => {
    const f = mount({ trigger: 100, stop: 95, target1: 110, target2: 120, acceptanceLevel: 99,
      stopLabel: 'Initial stop', targetSources: ['Resistance'], stopSources: ['Support'],
      target2Sources: ['Extension'], confirmedBy: [{ strategy: 'RSI', horizon: '2w' }] });
    const content = f.nativeElement.textContent;
    for (const label of ['Trigger', 'Initial stop', 'Target 1', 'Target 2', 'Acceptance level',
      'Target confirmed by', 'Stop confirmed by', 'Target 2 confirmed by', 'Confirmed by', 'RSI', '2w']) {
      expect(content).toContain(label);
    }
    f.componentRef.setInput('entry', 101);
    f.detectChanges();
    expect(f.nativeElement.querySelector('.levels').textContent).toContain('Entry');
    expect(f.nativeElement.querySelector('.levels').textContent).not.toContain('Trigger');
  });

  it('hides empty source lines and absent acceptance, confidence and explanation', () => {
    const f = mount();
    expect(f.nativeElement.textContent).not.toContain('confirmed by');
    expect(f.nativeElement.textContent).not.toContain('Acceptance level');
    expect(f.nativeElement.textContent).not.toContain('Confidence breakdown');
    expect(f.nativeElement.textContent).not.toContain('Why this trade');
    expect(f.nativeElement.querySelector('.gates').textContent).toContain('—');
    expect(f.nativeElement.textContent).toContain('None in the window');
  });

  it('renders signed confidence points, notes, muted unevaluated points and their total', () => {
    const f = mount({ confidencePoints: { trend: 3, earnings: 2, risk: -1 },
      confidenceUnevaluated: ['earnings'], confidenceFactors: [{ factor: 'trend', note: 'Rising' }] });
    expect(f.nativeElement.querySelector('.confidence').textContent).toContain('Rising');
    expect(f.nativeElement.querySelector('.confidence').textContent).toContain('+3');
    expect(f.nativeElement.querySelector('.confidence').textContent).toContain('−1');
    expect(f.nativeElement.querySelector('.total').textContent).toContain('+4');
    expect(f.nativeElement.querySelector('[title="no data — neutral points awarded"]')).not.toBeNull();
    expect(f.nativeElement.querySelector('.point.muted').textContent).toContain('+2');
  });

  it('falls back to text factors for null or empty points maps', () => {
    for (const confidencePoints of [null, {}]) {
      const f = mount({ confidencePoints, confidenceFactors: [{ factor: 'Trend', note: 'Aligned' }] });
      expect(f.nativeElement.querySelector('.confidence').textContent).toContain('Trend');
      expect(f.nativeElement.querySelector('.confidence').textContent).toContain('Aligned');
      expect(f.nativeElement.querySelector('.total')).toBeNull();
    }
  });

  it('shows quality even without confidence rows', () => {
    const f = mount({ qualityFactors: [{ label: 'Structure', points: -2 }] });
    expect(f.nativeElement.textContent).toContain('Quality breakdown');
    expect(f.nativeElement.querySelector('.quality').textContent).toContain('−2');
  });

  it('renders all gate fields and always shows the caveat outside collapsible content', () => {
    const f = mount({ gates: [gate(), gate({ key: 'regime', label: 'Regime', applies: false, margin: -2 })],
      status: 'ACTIVE', sessionsSinceCreated: 1 });
    expect(f.nativeElement.querySelectorAll('.gate-row')).toHaveLength(2);
    expect(f.nativeElement.querySelector('.gates').textContent).toContain('70');
    expect(f.nativeElement.querySelector('.gates').textContent).toContain('+10');
    expect(f.nativeElement.querySelector('.gates').textContent).toContain('Rank');
    expect(f.nativeElement.querySelector('.gates').textContent).toContain('Current rank');
    expect(f.nativeElement.querySelector('[title="off in current config"]').textContent).toContain('off');
    expect(f.nativeElement.querySelector('.caveat').tagName).toBe('P');
    expect(f.nativeElement.querySelector('.caveat').textContent).toBe(GATE_CAVEAT);
    expect(f.nativeElement.querySelector('details')).toBeNull();
    expect(f.nativeElement.querySelectorAll('.margin.pos')).toHaveLength(1);
    expect(f.nativeElement.querySelectorAll('.margin.neg')).toHaveLength(0);
  });

  it('colors only applying nonzero signed margins and uses one indicative chip', () => {
    const f = mount({ gates: [gate(), gate({ margin: -2 }), gate({ margin: 0 }), gate({ margin: null })],
      status: 'PARTIAL', sessionsSinceCreated: 5 });
    expect(f.nativeElement.querySelectorAll('.margin.pos')).toHaveLength(1);
    expect(f.nativeElement.querySelectorAll('.margin.neg')).toHaveLength(1);
    for (const sessionsSinceCreated of [null, 6]) {
      f.componentRef.setInput('sessionsSinceCreated', sessionsSinceCreated);
      f.detectChanges();
      expect(f.nativeElement.querySelectorAll('.margin.pos, .margin.neg')).toHaveLength(0);
      expect(f.nativeElement.querySelectorAll('.indicative')).toHaveLength(1);
    }
    f.componentRef.setInput('status', 'CLOSED');
    f.detectChanges();
    expect(f.nativeElement.querySelector('.indicative')).toBeNull();
  });

  it('renders calendar rows and respects requested sections', () => {
    const f = mount({ sections: ['calendar'], calendar: [{ date: '2026-10-16', kind: 'opex_monthly', label: 'Monthly OPEX' }] });
    expect(f.nativeElement.querySelectorAll('sb-panel')).toHaveLength(1);
    expect(f.nativeElement.textContent).toContain('2026-10-16');
    expect(f.nativeElement.textContent).toContain('Monthly OPEX');
  });

  it('retains the gate caveat for an empty gate list', () => {
    const f = mount({ sections: ['gates'] });
    expect(f.nativeElement.querySelector('.caveat').textContent).toBe(GATE_CAVEAT);
  });
});
