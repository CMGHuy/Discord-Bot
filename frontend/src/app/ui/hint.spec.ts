import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Hint } from './hint';

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

  it('gives the trigger a 44px target on touch and narrow screens', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 639px\) \{([\s\S]*?)\n    \}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain('min-width: var(--control-h)');
    expect(block![1]).toContain('min-height: var(--control-h)');
  });
});
