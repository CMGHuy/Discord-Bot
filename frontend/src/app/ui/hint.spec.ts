import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Hint, clampPopover, supportsPopover } from './hint';
import { POPOVER_OPEN_ATTR, installPopoverPolyfill } from '../testing/popover-polyfill';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/hint.ts'), 'utf8');

@Component({
  imports: [Hint],
  template: `
    <div>
      <span class="outside">Expectancy</span>
      <sb-hint text="Average R per closed trade, after costs." label="About expectancy" />
    </div>
  `,
})
class Host {}

describe('Hint (v80 D4)', () => {
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const hint = () => el().querySelector('sb-hint') as HTMLElement;
  const trigger = () => el().querySelector('sb-hint button') as HTMLButtonElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  const fire = (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
  };
  // The polyfill reflects :popover-open as an attribute (jsdom cannot match the pseudo-class).
  const isOpen = () => pop().hasAttribute(POPOVER_OPEN_ATTR);

  it('is closed at rest, and already describes its trigger', () => {
    expect(isOpen()).toBe(false);
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    expect(trigger().getAttribute('aria-label')).toBe('About expectancy');
    expect(trigger().getAttribute('aria-describedby')).toBe(pop().id);
    expect(pop().textContent!.trim()).toBe('Average R per closed trade, after costs.');
  });

  it('opens on hover and closes when the pointer leaves', () => {
    fire(hint(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    expect(trigger().getAttribute('aria-expanded')).toBe('true');
    fire(hint(), new MouseEvent('mouseleave'));
    expect(isOpen()).toBe(false);
  });

  it('opens on keyboard focus and closes when focus leaves', () => {
    fire(trigger(), new FocusEvent('focusin', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(trigger(), new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
    expect(isOpen()).toBe(false);
  });

  it('stays open after a tap, past the emulated hover ending, until tapped again', () => {
    // A phone tap fires mouseenter and focus before the click.
    fire(hint(), new MouseEvent('mouseenter'));
    fire(trigger(), new FocusEvent('focusin', { bubbles: true }));
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(hint(), new MouseEvent('mouseleave'));
    expect(isOpen()).toBe(true);
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('closes on Escape however it was opened', () => {
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(trigger(), new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('closes on a tap outside, and not on a tap inside the popover', () => {
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    fire(pop(), new MouseEvent('pointerdown', { bubbles: true }));
    expect(isOpen()).toBe(true);
    fire(el().querySelector('.outside')!, new MouseEvent('pointerdown', { bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('floats as an overlay, the one surface allowed a shadow', () => {
    expect(pop().classList).toContain('elev-overlay');
  });

  it('gives the trigger a 44px target on phone and tablet', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 1023px\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('min-width: var(--control-h)');
    expect(block![1]).toContain('min-height: var(--control-h)');
  });

  describe('top layer (v194 A1)', () => {
    afterEach(() => vi.restoreAllMocks());

    it('carries popover="manual" and no hidden attribute', () => {
      expect(supportsPopover()).toBe(true);
      expect(pop().getAttribute('popover')).toBe('manual');
      expect(pop().hasAttribute('hidden')).toBe(false);
    });

    it('opens and closes through showPopover() and hidePopover() on the popover element', () => {
      const show = vi.spyOn(HTMLElement.prototype, 'showPopover');
      const hide = vi.spyOn(HTMLElement.prototype, 'hidePopover');
      fire(hint(), new MouseEvent('mouseenter'));
      expect(show).toHaveBeenCalledTimes(1);
      expect(show.mock.contexts[0]).toBe(pop());
      expect(hide).not.toHaveBeenCalled();
      fire(hint(), new MouseEvent('mouseleave'));
      expect(hide).toHaveBeenCalledTimes(1);
      expect(hide.mock.contexts[0]).toBe(pop());
    });

    it('never shows twice or hides twice while open reasons overlap', () => {
      const show = vi.spyOn(HTMLElement.prototype, 'showPopover');
      const hide = vi.spyOn(HTMLElement.prototype, 'hidePopover');
      // A phone tap: emulated hover, then focus, then the pinning click.
      fire(hint(), new MouseEvent('mouseenter'));
      fire(trigger(), new FocusEvent('focusin', { bubbles: true }));
      fire(trigger(), new MouseEvent('click', { bubbles: true }));
      fire(hint(), new MouseEvent('mouseleave'));
      fire(trigger(), new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
      expect(isOpen()).toBe(true);
      expect(show).toHaveBeenCalledTimes(1);
      expect(hide).not.toHaveBeenCalled();
      fire(trigger(), new MouseEvent('click', { bubbles: true }));
      expect(isOpen()).toBe(false);
      expect(hide).toHaveBeenCalledTimes(1);
      // The strict polyfill throws on a double call, so reaching here also proves the guards.
    });

    it('tears down an open hint without throwing', () => {
      fire(trigger(), new MouseEvent('click', { bubbles: true }));
      expect(isOpen()).toBe(true);
      expect(() => fixture.destroy()).not.toThrow();
    });
  });

});

describe('Hint without the Popover API (v194 A1 fallback)', () => {
  const NAMES = ['showPopover', 'hidePopover', 'togglePopover'] as const;
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  const saved: Record<string, unknown> = {};
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    for (const name of NAMES) {
      saved[name] = proto[name];
      delete proto[name];
    }
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });

  afterEach(() => {
    for (const name of NAMES) proto[name] = saved[name];
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const hint = () => el().querySelector('sb-hint') as HTMLElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  const fire = (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
  };

  it('keeps the fixed-position path: no popover attribute, hidden by class until open', () => {
    expect(supportsPopover()).toBe(false);
    expect(pop().hasAttribute('popover')).toBe(false);
    expect(pop().classList).toContain('fallback-closed');
    fire(hint(), new MouseEvent('mouseenter'));
    expect(pop().classList).not.toContain('fallback-closed');
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    fire(hint(), new MouseEvent('mouseleave'));
    expect(pop().classList).toContain('fallback-closed');
  });
});

describe('popover polyfill (test environment, v194 A1)', () => {
  const make = () => {
    const element = document.createElement('div');
    element.setAttribute('popover', 'manual');
    document.body.appendChild(element);
    return element;
  };
  const errorName = (fn: () => unknown): string => {
    try {
      fn();
    } catch (error) {
      return (error as DOMException).name;
    }
    return 'no error';
  };

  it('is installed for every spec from test-setup.ts', () => {
    expect(typeof HTMLElement.prototype.showPopover).toBe('function');
  });

  it('reflects the open state as data-popover-open', () => {
    const element = make();
    element.showPopover();
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    element.hidePopover();
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    element.remove();
  });

  it('throws InvalidStateError on a double show, a double hide and a disconnected element', () => {
    const element = make();
    element.showPopover();
    expect(errorName(() => element.showPopover())).toBe('InvalidStateError');
    element.hidePopover();
    expect(errorName(() => element.hidePopover())).toBe('InvalidStateError');
    element.remove();
    expect(errorName(() => element.showPopover())).toBe('InvalidStateError');
  });

  it('throws NotSupportedError on an element without a popover attribute', () => {
    const element = document.createElement('div');
    document.body.appendChild(element);
    expect(errorName(() => element.showPopover())).toBe('NotSupportedError');
    element.remove();
  });

  it('togglePopover flips the state, honours force, and returns the new state', () => {
    const element = make();
    expect(element.togglePopover()).toBe(true);
    expect(element.togglePopover(true)).toBe(true);
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    expect(element.togglePopover()).toBe(false);
    expect(element.hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    element.remove();
  });

  it('rejects a closed disconnected popover even when toggling it closed', () => {
    const element = make();
    element.remove();
    expect(errorName(() => element.togglePopover(false))).toBe('InvalidStateError');
  });

  it('rejects a non-popover even when toggling it closed', () => {
    const element = document.createElement('div');
    document.body.appendChild(element);
    expect(errorName(() => element.togglePopover(false))).toBe('NotSupportedError');
    element.remove();
  });

  it('is idempotent: a second install keeps the installed methods', () => {
    const before = HTMLElement.prototype.showPopover;
    installPopoverPolyfill();
    expect(HTMLElement.prototype.showPopover).toBe(before);
  });
});

describe('clampPopover (v194 A1)', () => {
  const DESKTOP = { width: 1440, height: 900 };
  const PHONE = { width: 390, height: 844 };
  const POP = { width: 200, height: 50 };
  /** A 14px trigger whose top-left corner is at (left, top). */
  const trig = (left: number, top: number) => ({ top, bottom: top + 14, left, right: left + 14, width: 14 });

  it('sits 4px under the trigger, centred, when there is room', () => {
    expect(clampPopover(trig(200, 100), POP, DESKTOP, 'center')).toEqual({ top: 118, left: 107, above: false });
  });

  it("align 'left' ends the popover at the trigger's right edge", () => {
    expect(clampPopover(trig(400, 100), POP, DESKTOP, 'left')).toEqual({ top: 118, left: 214, above: false });
  });

  it('flips above the trigger when there is no room below', () => {
    expect(clampPopover(trig(200, 860), POP, DESKTOP, 'center')).toEqual({ top: 806, left: 107, above: true });
  });

  it('shifts left instead of running off the right edge, keeping 8px', () => {
    expect(clampPopover(trig(1420, 100), POP, DESKTOP, 'center').left).toBe(1440 - 8 - 200);
  });

  it('shifts right instead of running off the left edge, keeping 8px', () => {
    expect(clampPopover(trig(4, 100), POP, PHONE, 'center').left).toBe(8);
    expect(clampPopover(trig(20, 100), POP, PHONE, 'left').left).toBe(8);
  });

  it('pins a popover wider than the viewport to the left margin', () => {
    expect(clampPopover(trig(180, 100), { width: 500, height: 50 }, PHONE, 'center').left).toBe(8);
  });

  it('with no room either way, takes the larger side and keeps its top inside the margin', () => {
    const tall = { width: 200, height: 700 };
    const short = { width: 1440, height: 600 };
    // 300px above the trigger, 286px below it: above wins, then the top clamps to 8.
    expect(clampPopover(trig(200, 300), tall, short, 'center')).toEqual({ top: 8, left: 107, above: true });
    // 100px above, 486px below: stays below, clamped to 8 because it is taller than the viewport.
    expect(clampPopover(trig(200, 100), tall, short, 'center')).toEqual({ top: 8, left: 107, above: false });
  });

  it('takes the margin as a parameter', () => {
    expect(clampPopover(trig(1420, 100), POP, DESKTOP, 'center', 0).left).toBe(1240);
  });
});

