import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ICON_NAMES, Icon, IconName, IconSize } from './icon';

function render(name: string, size?: IconSize) {
  const f = TestBed.createComponent(Icon);
  f.componentRef.setInput('name', name as IconName);
  if (size !== undefined) f.componentRef.setInput('size', size);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

/** The absolute coordinates every `M` command moves to, in order. */
function moveTargets(d: string): number[] {
  return [...d.matchAll(/M\s*(-?[\d.]+)[\s,]+(-?[\d.]+)/g)].flatMap((m) => [Number(m[1]), Number(m[2])]);
}

/** The names that carry a filled sub-path (spec §4: Pending's sand,
 *  Opened's broadcast source, Partial's banked half). */
const FILLED: readonly IconName[] = ['pending', 'opened', 'partial'];

describe('Icon', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it.each([...ICON_NAMES])('renders an svg for %s', (name) => {
    expect(render(name).querySelector('svg')).not.toBeNull();
  });

  it.each([...ICON_NAMES])('draws %s on the 24 grid at a 1.8 round stroke', (name) => {
    const svg = render(name).querySelector('svg')!;
    expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
    expect(svg.getAttribute('stroke-width')).toBe('1.8');
    expect(svg.getAttribute('stroke-linecap')).toBe('round');
    expect(svg.getAttribute('stroke-linejoin')).toBe('round');
    // Every move target sits inside the 24 box: a path left on the old 16
    // grid would still pass this, which is why the drawings below are pinned.
    for (const value of moveTargets(svg.querySelector('path')!.getAttribute('d')!)) {
      expect(value, name).toBeGreaterThanOrEqual(0);
      expect(value, name).toBeLessThanOrEqual(24);
    }
  });

  it.each([...ICON_NAMES])('names %s when the caller gives no title', (name) => {
    // No icon is mute: the default tooltip is the label.
    expect(render(name).getAttribute('title')!.length, name).toBeGreaterThan(0);
  });

  it('draws 16px by default, the size of a table cell or a line of text', () => {
    const svg = render('trades').querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe('16');
    expect(svg.getAttribute('height')).toBe('16');
  });

  it.each([16, 20, 24] as const)('sets width and height to %ipx and keeps the 24 viewBox', (size) => {
    // Size is the caller's only lever: the drawing and its 1.8 stroke stay on
    // the 24 grid and scale with it, so no caller overrides the svg in CSS.
    const svg = render('trades', size).querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe(String(size));
    expect(svg.getAttribute('height')).toBe(String(size));
    expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
    expect(svg.getAttribute('stroke-width')).toBe('1.8');
  });

  it('follows a size change after the first render', () => {
    const f = TestBed.createComponent(Icon);
    f.componentRef.setInput('name', 'menu');
    f.detectChanges();
    f.componentRef.setInput('size', 20);
    f.detectChanges();
    const svg = (f.nativeElement as HTMLElement).querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe('20');
    expect(svg.getAttribute('height')).toBe('20');
  });

  it.each([...FILLED])('draws the filled part of %s as a second, solid path', (name) => {
    const paths = render(name).querySelectorAll('svg path');
    expect(paths).toHaveLength(2);
    const fill = paths[1];
    expect(fill.classList).toContain('fill');
    expect(fill.getAttribute('fill')).toBe('currentColor');
    expect(fill.getAttribute('stroke')).toBe('none');
    expect(paths[0].classList).not.toContain('fill');
  });

  it('draws every other name as one stroked path', () => {
    for (const name of ICON_NAMES.filter((n) => !FILLED.includes(n))) {
      expect(render(name).querySelectorAll('svg path'), name).toHaveLength(1);
    }
  });

  it('banks the right half of the partial circle', () => {
    const paths = render('partial').querySelectorAll('svg path');
    expect(paths[0].getAttribute('d')).toBe('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z');
    expect(paths[1].getAttribute('d')).toBe('M12 3a9 9 0 0 1 0 18z');
  });

  it('has a path for the calendar icon', () => {
    expect(ICON_NAMES).toContain('calendar');
  });

  it('renders nothing for an unknown name, and does not throw', () => {
    // A missing icon should leave a gap, not take the screen down with it.
    expect(() => render('not-an-icon')).not.toThrow();
    expect(render('not-an-icon').querySelector('svg')).toBeNull();
  });

  it('inherits its colour from the control it sits in', () => {
    // currentColor is what lets one sprite serve an active nav entry, a
    // hovered one and a disabled one without three copies of the path data.
    const svg = render('trades').querySelector('svg')!;
    expect(svg.getAttribute('stroke')).toBe('currentColor');
    expect(svg.getAttribute('fill')).toBe('none');
  });

  it('is hidden from assistive tech', () => {
    // The label always lives on the parent control. An icon that announces
    // itself as well produces "Trades Trades" on every nav entry.
    expect(render('trades').querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('covers every name the shell needs', () => {
    for (const needed of ['dashboard', 'trades', 'analytics', 'watchlist', 'risk',
                          'system', 'collapse', 'expand', 'profile', 'signout', 'menu', 'search']) {
      expect(ICON_NAMES, `missing icon: ${needed}`).toContain(needed);
    }
  });

  it('keeps every existing name in its place (callers reach the redraw untouched)', () => {
    expect(ICON_NAMES.slice(0, 27)).toEqual([
      'dashboard', 'trades', 'analytics', 'calendar', 'watchlist', 'risk', 'system', 'versions',
      'collapse', 'expand', 'profile', 'signout', 'menu', 'trash', 'clock', 'more', 'opened',
      'closed', 'pending', 'partial', 'cancelled', 'trailing', 'brand', 'reports', 'research',
      'search', 'theme',
    ]);
  });

  it('appends the nine new names after the existing 27, in order (spec §4)', () => {
    expect(ICON_NAMES).toHaveLength(36);
    expect(ICON_NAMES.slice(27)).toEqual([
      'info', 'long', 'short', 'close', 'edit', 'up', 'down', 'plus', 'minus',
    ]);
  });

  it.each([
    ['info', 'Information'],
    ['long', 'Long'],
    ['short', 'Short'],
    ['close', 'Close'],
    ['edit', 'Edit'],
    ['up', 'Move up'],
    ['down', 'Move down'],
    ['plus', 'Add'],
    ['minus', 'Remove'],
  ] as const)('labels %s as "%s" when the caller gives no title', (name, label) => {
    expect(render(name).getAttribute('title')).toBe(label);
  });

  it('has no grip: the tab editor has no drag-reorder, so nothing should look draggable', () => {
    expect(ICON_NAMES as readonly string[]).not.toContain('grip');
  });

  it('draws the destinations as what they mean (spec §4)', () => {
    const d = (name: string) => render(name).querySelector('svg path')!.getAttribute('d');
    // A gauge with a needle, not the old 2x2 grid of panels.
    expect(d('dashboard')).toBe('M3.5 17a8.5 8.5 0 0 1 17 0 M12 8.5V10 M6.6 10.6l1 1 M17.4 10.6l-1 1 M12 17l3.6-4.6 M3.5 20h17');
    // Binoculars, not an eye (an eye reads as show/hide).
    expect(d('watchlist')).toMatch(/^M6\.5 19\.5a3\.5 3\.5 0 1 0 0-7/);
    // The light bulb with a rising line: the spec's drawing, not mockup 4's bars.
    expect(d('analytics')).toContain('M9.5 10.5l1.7-1.7 1.6 1.6 1.9-2');
    // A shield with a percent sign.
    expect(d('risk')).toContain('M9.3 15.2l5.4-6.4');
    // A monitor with a pulse line, not a gear.
    expect(d('system')).toBe('M3 4h18v12H3z M8 20h8 M12 16v4 M5.5 10h3l1.5-3 2 6 1.5-3h5');
    // A finish flag: neutral for winners and losers.
    expect(d('closed')).toBe('M5 21V4 M5 4h13l-2.5 4L18 12H5');
  });

  it('renders the trash icon', () => {
    expect(ICON_NAMES).toContain('trash');
  });

  it('carries the icons the v85 chrome and feed need', () => {
    for (const name of ['clock', 'more', 'opened', 'closed'] as const) {
      expect(ICON_NAMES).toContain(name);
    }
  });

  it('renders the brand icon, named Bomeo Capital by default (R1-14, v247)', () => {
    expect(ICON_NAMES).toContain('brand');
    expect(render('brand').querySelector('svg path')).not.toBeNull();
    expect(render('brand').getAttribute('title')).toBe('Bomeo Capital');
  });

  it('carries the search glyph the top bar and the phone bar use (v195 correction 1)', () => {
    expect(ICON_NAMES).toContain('search');
    expect(render('search').querySelector('svg path')).not.toBeNull();
    // Named by its default label when the caller gives none.
    expect(render('search').getAttribute('title')).toBe('Search');
  });

  it('draws the theme toggle as a crescent moon (v240: both themes are dark)', () => {
    expect(ICON_NAMES).toContain('theme');
    const path = render('theme').querySelector('svg path')!;
    expect(path.getAttribute('d')).toBe('M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z');
    expect(render('theme').getAttribute('title')).toBe('Theme');
  });

  it('never draws two names with the same glyph -- an icon-only rail reads by shape', () => {
    const glyphs = new Map<string, string>();
    for (const name of ICON_NAMES) {
      const d = render(name).querySelector('svg path')!.getAttribute('d')!;
      expect(glyphs.get(d), `${name} draws the same glyph as ${glyphs.get(d)}`).toBeUndefined();
      glyphs.set(d, name);
    }
  });
});
