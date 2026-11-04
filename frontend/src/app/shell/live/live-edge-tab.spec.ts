import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveEdgeTab, liveSummaryLabel } from './live-edge-tab';
import { LiveWarning, warningLabel } from './live-state';

const HEAT = 'Heat 2,010 € · 4.2% / 6%';
const ALL: LiveWarning[] = ['heat-near-cap', 'over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch'];

describe('liveSummaryLabel', () => {
  it('reads the heat and the count when calm', () => {
    expect(liveSummaryLabel([], HEAT, 3)).toBe(`Open the live dock. ${HEAT}. 3 awaiting order`);
    expect(liveSummaryLabel([], 'Heat —', null)).toBe('Open the live dock. Heat —');
  });
  it('names every warning, in order', () => {
    expect(liveSummaryLabel(['heat-near-cap', 'stale'], HEAT, 0))
      .toBe(`Open the live dock. Warning: Heat near cap, Data stale. ${HEAT}. 0 awaiting order`);
  });
});

describe('LiveEdgeTab', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(warnings: LiveWarning[], awaitingCount: number | null = 3) {
    const fixture = TestBed.createComponent(LiveEdgeTab);
    fixture.componentRef.setInput('warnings', warnings);
    fixture.componentRef.setInput('heatText', HEAT);
    fixture.componentRef.setInput('awaitingCount', awaitingCount);
    fixture.detectChanges();
    return { fixture, button: (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button.edge-tab')! };
  }

  it('shows the dot, the word Live, the heat figure and the count', () => {
    const { button } = mount([]);
    expect(button.querySelector('.dot')).not.toBeNull();
    expect(button.querySelector('.word')!.textContent!.trim()).toBe('Live');
    expect(button.querySelector('.heat')!.textContent!.trim()).toBe(HEAT);
    expect(button.querySelector('.count')!.textContent!.trim()).toBe('3');
    expect(button.classList).not.toContain('warn');
    expect(button.classList).toContain('sb-hit');
    expect(button.getAttribute('aria-label')).toBe(`Open the live dock. ${HEAT}. 3 awaiting order`);
  });

  it.each(ALL)('takes the warning tone and names it for %s', (warning) => {
    const { button } = mount([warning]);
    expect(button.classList).toContain('warn');
    expect(button.getAttribute('aria-label')).toContain(`Warning: ${warningLabel(warning)}`);
  });

  it('omits the count before /live answers', () => {
    expect(mount([], null).button.querySelector('.count')).toBeNull();
  });

  it('asks to expand on a tap, and only then', () => {
    const { fixture, button } = mount(['stale']);
    let expanded = 0;
    fixture.componentInstance.expand.subscribe(() => expanded++);
    expect(expanded).toBe(0);
    button.click();
    expect(expanded).toBe(1);
  });
});
