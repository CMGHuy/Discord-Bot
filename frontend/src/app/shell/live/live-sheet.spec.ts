import { Component, input, output, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveDock } from './live-dock';
import { LiveSheet } from './live-sheet';

@Component({
  selector: 'sb-live-dock',
  template: '<button type="button" class="first">First</button><button type="button" class="dock-close" (click)="close.emit()">Close</button>',
})
class StubDock {
  readonly variant = input<'docked' | 'sheet'>('docked');
  // eslint-disable-next-line @angular-eslint/no-output-native
  readonly close = output<void>();
}

describe('LiveSheet (v203)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    TestBed.overrideComponent(LiveSheet, { remove: { imports: [LiveDock] }, add: { imports: [StubDock] } });
  });

  function mount(open: boolean, side: 'right' | 'bottom' = 'right') {
    const fixture = TestBed.createComponent(LiveSheet);
    fixture.componentRef.setInput('open', open);
    fixture.componentRef.setInput('side', side);
    fixture.detectChanges();
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => closed++);
    return { fixture, el: fixture.nativeElement as HTMLElement, closed: () => closed };
  }
  const escape = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

  it('renders nothing while closed, and ignores Escape then', () => {
    const { el, closed } = mount(false);
    expect(el.querySelector('[role=dialog]')).toBeNull();
    expect(el.querySelector('.scrim')).toBeNull();
    escape();
    expect(closed()).toBe(0);
  });

  it('opens from the right as a labelled modal holding the dock in its sheet variant', () => {
    const { fixture, el } = mount(true, 'right');
    const dialog = el.querySelector('[role=dialog]')!;
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBe('Live');
    expect(dialog.classList).toContain('right');
    expect(dialog.classList).not.toContain('sb-sheet-in');
    expect(fixture.debugElement.query(By.directive(StubDock)).componentInstance.variant()).toBe('sheet');
  });

  it('rises from the bottom on a phone', () => {
    const dialog = mount(true, 'bottom').el.querySelector('[role=dialog]')!;
    expect(dialog.classList).toContain('bottom');
    expect(dialog.classList).toContain('sb-sheet-in');
  });

  it('traps focus: the first control takes it, and Tab wraps from the last', () => {
    const { el } = mount(true);
    expect(document.activeElement).toBe(el.querySelector('button.first'));
    const last = el.querySelector<HTMLButtonElement>('button.dock-close')!;
    last.focus();
    last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    expect(document.activeElement).toBe(el.querySelector('button.first'));
  });

  it('closes on Escape, on a scrim tap and from the dock', () => {
    const { el, closed } = mount(true);
    escape();
    el.querySelector<HTMLElement>('.scrim')!.click();
    el.querySelector<HTMLButtonElement>('button.dock-close')!.click();
    expect(closed()).toBe(3);
  });
});
