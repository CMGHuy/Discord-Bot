import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Flash } from './flash';

@Component({
  imports: [Flash],
  template: `<span [sbFlash]="value()">{{ value() }}</span>`,
})
class Host { value = signal(1); }

function setup() {
  const f = TestBed.createComponent(Host);
  f.detectChanges();
  return { f, span: (f.nativeElement as HTMLElement).querySelector('span')! };
}

describe('Flash', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('does not flash on first render', () => {
    // Everything is "new" on arrival; flashing every cell would be a
    // full-screen strobe on load.
    expect(setup().span.classList.contains('flash-up')).toBe(false);
  });

  it('flashes up when the value rises', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(2);
    f.detectChanges();
    expect(span.classList.contains('flash-up')).toBe(true);
  });

  it('flashes down when the value falls', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(0);
    f.detectChanges();
    expect(span.classList.contains('flash-down')).toBe(true);
  });

  it('does not flash when a re-render reports the same value', () => {
    const { f, span } = setup();
    f.componentInstance.value.set(1);
    f.detectChanges();
    expect(span.className).toBe('');
  });
});
