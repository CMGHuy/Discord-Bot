import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ICON_NAMES, Icon, IconName } from './icon';

function render(name: string) {
  const f = TestBed.createComponent(Icon);
  f.componentRef.setInput('name', name as IconName);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('Icon', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it.each([...ICON_NAMES])('renders an svg for %s', (name) => {
    expect(render(name).querySelector('svg')).not.toBeNull();
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
                          'system', 'collapse', 'expand', 'profile', 'signout', 'menu']) {
      expect(ICON_NAMES, `missing icon: ${needed}`).toContain(needed);
    }
  });
});
