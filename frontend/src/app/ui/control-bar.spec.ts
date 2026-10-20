import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ControlBar } from './control-bar';

@Component({
  imports: [ControlBar],
  template: `
    <sb-control-bar [activeCount]="count" (cleared)="cleared = true">
      <button filters id="chip">Open</button>
      <select scope id="range"><option>YTD</option></select>
    </sb-control-bar>
  `,
})
class Host {
  count = 0;
  cleared = false;
}

function host(count: number) {
  const f = TestBed.createComponent(Host);
  f.componentInstance.count = count;
  f.detectChanges();
  return f;
}

describe('ControlBar (v85 D22)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('projects filters into the leading slot', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.filters #chip')).not.toBeNull();
  });

  it('projects scope controls into the trailing slot', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.scope #range')).not.toBeNull();
  });

  it('hides Clear when nothing is filtered', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.clear')).toBeNull();
  });

  it('shows the active count when something is filtered', () => {
    const el = host(3).nativeElement as HTMLElement;
    expect(el.querySelector('.clear')!.textContent).toContain('3');
  });

  it('emits cleared when Clear is pressed', () => {
    const f = host(2);
    (f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.clear')!.click();
    expect(f.componentInstance.cleared).toBe(true);
  });

  it('names itself for assistive tech', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.bar')!.getAttribute('aria-label')).toBe('Page controls');
  });
});

const CONTROL_BAR_SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/control-bar.ts'), 'utf8');

describe('ControlBar one row pattern (v179 §3.3)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  // The phone block, whatever it contains, as one string.
  const phoneBlock = () =>
    CONTROL_BAR_SOURCE.match(/@media \(max-width: 639px\) \{([\s\S]*?)\n    \}/)?.[1] ?? '';

  it('stacks at the declared phone breakpoint, not one pixel into tablet', () => {
    // 640px is the first `sm` (tablet) width -- BREAKPOINTS.sm in breakpoints.ts.
    expect(CONTROL_BAR_SOURCE).toContain('@media (max-width: 639px)');
    expect(CONTROL_BAR_SOURCE).not.toContain('max-width: 640px');
  });

  it('lays phone filters out as two equal columns instead of a ragged wrap', () => {
    expect(phoneBlock()).toMatch(
      /\.filters \{[^}]*display: grid;[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
    );
  });

  it('keeps every projected control reachable -- the grid only re-arranges them', () => {
    const el = host(0).nativeElement as HTMLElement;
    expect(el.querySelector('.filters #chip')).not.toBeNull();
    expect(el.querySelector('.scope #range')).not.toBeNull();
  });
});
