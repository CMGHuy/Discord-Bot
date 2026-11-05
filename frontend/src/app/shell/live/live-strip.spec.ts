import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveWarning, warningLabel } from './live-state';
import { LiveStrip } from './live-strip';

const NOW = new Date('2026-10-29T13:00:00Z');
const ago = (min: number) => new Date(NOW.getTime() - min * 60_000).toISOString();
const HEAT = 'Heat 2,010 € · 4.2% / 6%';
const ALL: LiveWarning[] = ['heat-near-cap', 'over-cap', 'stale', 'disconnected', 'bot-down', 'killswitch'];

describe('LiveStrip (v203)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function mount(warnings: LiveWarning[], awaitingCount: number | null = 3, lastSuccess: string | null = ago(6)) {
    const fixture = TestBed.createComponent(LiveStrip);
    fixture.componentRef.setInput('warnings', warnings);
    fixture.componentRef.setInput('heatText', HEAT);
    fixture.componentRef.setInput('awaitingCount', awaitingCount);
    fixture.componentRef.setInput('lastSuccess', lastSuccess);
    fixture.componentRef.setInput('now', NOW);
    fixture.detectChanges();
    return { fixture, button: (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button.live-strip')! };
  }
  const text = (button: HTMLElement, selector: string) => button.querySelector(selector)?.textContent?.trim() ?? null;

  it('reads dot, scan age, heat, awaiting count and Live ›, in that order', () => {
    const { button } = mount([]);
    expect([...button.children].map((child) => child.className.split(' ')[0])).toEqual(['dot', 'age', 'heat', 'count', 'go']);
    expect(text(button, '.age')).toBe('6m ago');
    expect(text(button, '.heat')).toBe(HEAT);
    expect(text(button, '.count')).toBe('3 awaiting order');
    expect(text(button, '.go')).toBe('Live ›');
    expect(button.classList).not.toContain('warn');
    expect(button.classList).toContain('sb-hit');
    expect(button.getAttribute('aria-haspopup')).toBe('dialog');
    expect(button.getAttribute('aria-label')).toBe(`Open the live dock. ${HEAT}. 3 awaiting order. Last scan 6m ago`);
  });

  it.each(ALL)('takes the edge tab warning tone and names %s', (warning) => {
    const { button } = mount([warning]);
    expect(button.classList).toContain('warn');
    expect(button.getAttribute('aria-label')).toContain(`Warning: ${warningLabel(warning)}`);
  });

  it('turns the heat amber only for a heat warning', () => {
    expect(mount(['heat-near-cap']).button.querySelector('.heat')!.classList).toContain('near');
    expect(mount(['over-cap']).button.querySelector('.heat')!.classList).toContain('near');
    expect(mount(['stale']).button.querySelector('.heat')!.classList).not.toContain('near');
  });

  it('says No scan yet without a success, and omits the count before /live answers', () => {
    const { button } = mount([], null, null);
    expect(text(button, '.age')).toBe('No scan yet');
    expect(button.querySelector('.count')).toBeNull();
  });

  it('asks for the sheet on a tap', () => {
    const { fixture, button } = mount([]);
    let opened = 0;
    fixture.componentInstance.opened.subscribe(() => opened++);
    button.click();
    expect(opened).toBe(1);
  });
});
