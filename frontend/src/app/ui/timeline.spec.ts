import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Timeline, TimelineItem } from './timeline';

const ITEMS: TimelineItem[] = [
  { id: 'ui-2.14.0', title: 'v2.14.0', meta: 'UI · 22 Apr 2024', current: true },
  { id: 'ui-2.13.1', title: 'v2.13.1', meta: 'UI · 10 Apr 2024', current: false },
];

function render(items = ITEMS): HTMLElement {
  const f = TestBed.createComponent(Timeline);
  f.componentRef.setInput('items', items);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.timeline')!;
}

describe('Timeline (v85 D28)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders one entry per item', () => {
    expect(render().querySelectorAll('.entry').length).toBe(2);
  });

  it('renders the title and meta line', () => {
    const first = render().querySelector('.entry')!;
    expect(first.querySelector('.title')!.textContent).toContain('v2.14.0');
    expect(first.querySelector('.meta')!.textContent).toContain('UI · 22 Apr 2024');
  });

  it('marks the current release with a word, not only a filled dot', () => {
    const first = render().querySelector('.entry')!;
    expect(first.classList).toContain('current');
    expect(first.querySelector('.badge')!.textContent).toContain('Current');
  });

  it('leaves earlier releases unmarked', () => {
    expect(render().querySelectorAll('.entry')[1].querySelector('.badge')).toBeNull();
  });

  it('renders an ordered list so the sequence survives without CSS', () => {
    expect(render().querySelector('ol')).not.toBeNull();
  });

  it('renders nothing but an empty rail for an empty list', () => {
    expect(render([]).querySelectorAll('.entry').length).toBe(0);
  });
});
