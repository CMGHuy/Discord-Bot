import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { FocusTrap } from './focus-trap';

@Component({
  imports: [FocusTrap],
  template: `
    <button id="opener" (click)="open.set(true)">Open</button>
    @if (open()) {
      <div sbFocusTrap>
        <button id="first">First</button>
        <button id="last">Last</button>
      </div>
    }
  `,
})
class Host { open = signal(false); }

describe('FocusTrap', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('moves focus into the panel when it opens', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    f.componentInstance.open.set(true);
    f.detectChanges();
    expect(document.activeElement?.id).toBe('first');
  });

  it('returns focus to whatever opened it', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    document.getElementById('opener')!.focus();
    f.componentInstance.open.set(true);
    f.detectChanges();
    f.componentInstance.open.set(false);
    f.detectChanges();
    expect(document.activeElement?.id).toBe('opener');
  });

  it('wraps Tab from the last focusable back to the first', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    f.componentInstance.open.set(true);
    f.detectChanges();
    document.getElementById('last')!.focus();
    const el = f.nativeElement as HTMLElement;
    const trap = el.querySelector('[sbFocusTrap]')!;
    const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    trap.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement?.id).toBe('first');
  });

  it('wraps Shift+Tab from the first focusable back to the last', () => {
    const f = TestBed.createComponent(Host);
    f.detectChanges();
    f.componentInstance.open.set(true);
    f.detectChanges();
    document.getElementById('first')!.focus();
    const el = f.nativeElement as HTMLElement;
    const trap = el.querySelector('[sbFocusTrap]')!;
    const event = new KeyboardEvent('keydown', {
      key: 'Tab', shiftKey: true, bubbles: true, cancelable: true,
    });
    trap.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement?.id).toBe('last');
  });
});
