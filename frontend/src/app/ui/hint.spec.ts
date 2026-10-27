import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Hint } from './hint';
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
  const isOpen = () => !pop().hidden;

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

  it('is idempotent: a second install keeps the installed methods', () => {
    const before = HTMLElement.prototype.showPopover;
    installPopoverPolyfill();
    expect(HTMLElement.prototype.showPopover).toBe(before);
  });
});

