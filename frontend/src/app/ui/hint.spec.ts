import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection, signal, viewChild } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DIALOG_CLOSING_EVENT, HINT_HOVER_DELAY_MS, Hint, clampPopover, placeAbove, placeBeside, supportsPopover } from './hint';
import { ConfirmDialog } from './confirm-dialog';
import { Drawer } from './layout';
import { provideMotion } from './motion/motion.service';
import { installDialogPolyfill } from '../testing/dialog-polyfill';
import { POPOVER_OPEN_ATTR, installPopoverPolyfill } from '../testing/popover-polyfill';
import { allSources, stripComments } from './testing/all-sources';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/hint.ts'), 'utf8');

/** icon.ts's `info` drawing (V241-2): a circle, a stem and a dot. */
const INFO_D = 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5.5 M12 7.6v.1';

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

/** v195 correction 10: a rail-style link with its label hint beside it. */
@Component({
  imports: [Hint],
  template: `
    <a #link href="/dashboard" class="rail-link" aria-label="Dashboard">D</a>
    <sb-hint [anchor]="anchored() ? link : null" text="Dashboard" />
    <span class="outside">Elsewhere</span>
  `,
})
class AnchorHost {
  readonly anchored = signal(true);
}

/** v247 Decision 6: a rail-style label and a glyph hint, both with the hover delay. */
@Component({
  imports: [Hint],
  template: `
    <a #a href="/dashboard" class="link-a" aria-label="Dashboard">D</a>
    <sb-hint class="anchored-hint" [anchor]="a" text="Dashboard" [openDelay]="delay" />
    <sb-hint class="glyph-hint" text="Explained." label="About it" [openDelay]="delay" />
  `,
})
class DelayHost {
  readonly delay = HINT_HOVER_DELAY_MS;
}

/** v247 Decision 7: two rail labels and a glyph hint on one page. */
@Component({
  imports: [Hint],
  template: `
    <a #a href="/dashboard" class="link-a" aria-label="Dashboard">D</a>
    <sb-hint [anchor]="a" text="Dashboard" />
    <a #b href="/watchlist" class="link-b" aria-label="Watchlist">W</a>
    <sb-hint [anchor]="b" text="Watchlist" />
    <sb-hint class="glyph-hint" text="Explained." label="About it" />
    <span class="outside">Elsewhere</span>
  `,
})
class PairHost {}

/** v247: a tab-bar tab with its name above it, and a rail label beside its link. */
@Component({
  imports: [Hint],
  template: `
    <a #tab href="/trades" class="tab" aria-label="Trades">T</a>
    <sb-hint #tip [anchor]="tab" text="Trades" placement="above" />
    <a #rail href="/dashboard" class="rail-link" aria-label="Dashboard">D</a>
    <sb-hint #railTip [anchor]="rail" text="Dashboard" />
    <span class="outside">Elsewhere</span>
  `,
})
class PinHost {
  readonly tip = viewChild.required<Hint>('tip');
  readonly railTip = viewChild.required<Hint>('railTip');
}

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

  it('draws the info icon in its trigger, not a letter in a circle (v240 §4)', () => {
    const icon = trigger().querySelector(':scope > sb-icon');
    expect(icon).not.toBeNull();
    expect(icon!.querySelector('svg path')!.getAttribute('d')).toBe(INFO_D);
    // No text left in the button: the shape no longer depends on the font.
    expect(trigger().textContent!.trim()).toBe('');
    expect(trigger().querySelector('.glyph')).toBeNull();
  });

  it('keeps the name on the button and out of the icon', () => {
    // One name per control: "About expectancy", never "About expectancy Information".
    expect(trigger().getAttribute('aria-label')).toBe('About expectancy');
    expect(trigger().getAttribute('aria-describedby')).toBe(pop().id);
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
    const icon = trigger().querySelector('sb-icon')!;
    expect(icon.getAttribute('title')).toBe('');
    expect(icon.querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
    expect(trigger().querySelectorAll('[aria-label]')).toHaveLength(0);
  });

  it('draws the icon at the inline size, 16px', () => {
    expect(trigger().querySelector('sb-icon svg')!.getAttribute('width')).toBe('16');
  });

  it('has no glyph input and no glyph rule left', () => {
    expect(SOURCE).not.toMatch(/\bglyph\s*=\s*input\b/);
    expect(SOURCE).not.toMatch(/\.glyph\s*\{/);
  });

  it('is never handed a glyph by a caller: a static glyph= would be a dead attribute', () => {
    // strictTemplates does not reject an unknown static attribute on a
    // component, so a leftover glyph="v" would build, render nothing and
    // mislead the next reader. Scan every template instead.
    const offenders = allSources()
      .filter(({ source }) => /<sb-hint\b[^>]*\bglyph=/.test(stripComments(source)))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });

  it('floats as an overlay, the one surface allowed a shadow', () => {
    expect(pop().classList).toContain('elev-overlay');
  });

  /** The component's touch-width style block (closed by a 4-space-indented brace). */
  const touchBlock = () => SOURCE.match(/@media \(pointer: coarse\), \(max-width: 1023px\) \{([\s\S]*?)\n {4}\}/);

  it('gives the trigger a 44px target on phone and tablet', () => {
    const block = touchBlock();
    expect(block).not.toBeNull();
    expect(block![1]).toContain('.trigger::after');
    expect(block![1]).toContain('position: absolute');
    expect(block![1]).toContain('width: var(--control-h); height: var(--control-h)');
  });

  it('keeps the 44px target out of layout, so a hint never makes its row taller', () => {
    const block = touchBlock();
    expect(block![1]).not.toContain('min-height');
    expect(block![1]).not.toContain('min-width');
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

@Component({
  imports: [Drawer, Hint],
  template: `
    <sb-drawer [open]="open()" heading="AAPL">
      <sb-hint text="Leg 1 of 2 of one plan." label="About legs" />
    </sb-drawer>
  `,
})
class DrawerHost {
  readonly open = signal(true);
}

describe('Hint inside a closing dialog host (v194 A1)', () => {
  let fixture: ComponentFixture<DrawerHost>;

  beforeEach(() => {
    installDialogPolyfill();
    // Motion on, so the drawer's exit is still running when we look: the hint
    // must hide when the close STARTS, not when the dialog finally closes.
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
    fixture = TestBed.createComponent(DrawerHost);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const dialog = () => el().querySelector('sb-drawer dialog') as HTMLDialogElement;
  const trigger = () => el().querySelector('sb-hint button') as HTMLButtonElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  /** Twice: the host's close sets the hint's signals, which need their own pass. */
  const settle = () => {
    fixture.detectChanges();
    fixture.detectChanges();
  };

  it('hides a pinned hint as soon as the drawer starts its exit', () => {
    trigger().click();
    settle();
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    (el().querySelector('sb-drawer button.close') as HTMLButtonElement).click();
    settle();
    expect(dialog().hasAttribute('open')).toBe(true); // the exit animation is still running
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
    expect(trigger().getAttribute('aria-expanded')).toBe('false');
  });

  it('hides a pinned hint when its dialog closes without the drawer exit', () => {
    trigger().click();
    settle();
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    dialog().close();
    settle();
    expect(dialog().hasAttribute('open')).toBe(false);
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(false);
  });

  it('removes the pinned hint when the drawer open input becomes false', () => {
    trigger().click();
    settle();
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    fixture.componentInstance.open.set(false);
    settle();
    expect(dialog().hasAttribute('open')).toBe(false);
    expect(el().querySelector('sb-hint [role=tooltip]')).toBeNull();
  });

  it('ignores a closing event on some other dialog', () => {
    trigger().click();
    settle();
    const other = document.createElement('dialog');
    document.body.appendChild(other);
    other.dispatchEvent(new Event(DIALOG_CLOSING_EVENT));
    settle();
    expect(pop().hasAttribute(POPOVER_OPEN_ATTR)).toBe(true);
    other.remove();
  });
});

@Component({
  imports: [ConfirmDialog],
  template: `<sb-confirm-dialog [open]="true" title="Close AAPL" consequence="The paper trade closes at the last price." />`,
})
class ConfirmHost {}

describe('ConfirmDialog announces its close (v194 A1)', () => {
  it('dispatches a non-bubbling sb-dialog-closing on its <dialog> when Cancel starts the exit', () => {
    installDialogPolyfill();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideMotion('on')] });
    const fixture = TestBed.createComponent(ConfirmHost);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const seen: Event[] = [];
    root.querySelector('dialog')!.addEventListener(DIALOG_CLOSING_EVENT, (event) => seen.push(event));
    const cancel = [...root.querySelectorAll('button')].find((b) => b.textContent!.trim() === 'Cancel')!;
    cancel.click();
    fixture.detectChanges();
    expect(seen).toHaveLength(1);
    expect(seen[0].bubbles).toBe(false);
    expect(DIALOG_CLOSING_EVENT).toBe('sb-dialog-closing');
  });
});

describe('Hint anchor (label) mode (v195 correction 10)', () => {
  let fixture: ComponentFixture<AnchorHost>;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(AnchorHost);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const link = () => el().querySelector('a.rail-link') as HTMLAnchorElement;
  const pop = () => el().querySelector('sb-hint [role=tooltip]') as HTMLElement;
  const fire = async (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
    await fixture.whenStable();
  };
  const isOpen = () => pop().hasAttribute(POPOVER_OPEN_ATTR);

  it('draws no info icon in anchor mode: the rail link is the thing being named', () => {
    expect((fixture.nativeElement as HTMLElement).querySelector('sb-hint sb-icon')).toBeNull();
  });

  it('renders no trigger button, so the rail link stays the only tab stop', () => {
    expect(el().querySelectorAll('sb-hint button')).toHaveLength(0);
    expect(pop().hasAttribute('tabindex')).toBe(false);
    expect(el().querySelector('sb-hint')!.classList).toContain('anchored');
  });

  it('describes the anchor with the label popover, closed at rest', () => {
    expect(link().getAttribute('aria-describedby')).toBe(pop().id);
    expect(pop().textContent!.trim()).toBe('Dashboard');
    expect(pop().classList).toContain('label');
    expect(isOpen()).toBe(false);
  });

  it('opens on the anchor hover and closes when the pointer leaves it', async () => {
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    await fire(link(), new MouseEvent('mouseleave'));
    expect(isOpen()).toBe(false);
  });

  it('opens on the anchor keyboard focus and closes on blur', async () => {
    await fire(link(), new FocusEvent('focus'));
    expect(isOpen()).toBe(true);
    await fire(link(), new FocusEvent('blur'));
    expect(isOpen()).toBe(false);
  });

  it('closes on Escape on the anchor without moving focus away', async () => {
    await fire(link(), new FocusEvent('focus'));
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    await fire(link(), new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(isOpen()).toBe(false);
  });

  it('ignores other keys on the anchor', async () => {
    await fire(link(), new FocusEvent('focus'));
    await fire(link(), new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(isOpen()).toBe(true);
  });

  it('closes on a press of the anchor and stays closed past the focus that press causes', async () => {
    // A rail click: hover opened the label, the press must close it, and the
    // focus the browser then gives the link must not reopen it (it would stay
    // beside the link after navigation until blur).
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    await fire(link(), new Event('pointerdown', { bubbles: true }));
    expect(isOpen()).toBe(false);
    await fire(link(), new FocusEvent('focus'));
    expect(isOpen()).toBe(false);
  });

  it('opens on keyboard focus again after a press has come and gone', async () => {
    await fire(link(), new Event('pointerdown', { bubbles: true }));
    await fire(link(), new FocusEvent('focus'));
    await fire(link(), new FocusEvent('blur'));
    await fire(link(), new FocusEvent('focus'));
    expect(isOpen()).toBe(true);
  });

  it('unbinds when the anchor goes away and falls back to the glyph trigger', async () => {
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(true);
    fixture.componentInstance.anchored.set(false);
    fixture.detectChanges();
    await fixture.whenStable();
    expect(isOpen()).toBe(false);
    expect(link().hasAttribute('aria-describedby')).toBe(false);
    await fire(link(), new MouseEvent('mouseenter'));
    expect(isOpen()).toBe(false);
    expect(el().querySelector('sb-hint button.trigger')).not.toBeNull();
    expect(el().querySelector('sb-hint')!.classList).not.toContain('anchored');
  });
});

describe('placeBeside (v195 correction 10)', () => {
  const rail = { top: 100, bottom: 140, left: 0, right: 48, width: 48 };
  const label = { width: 80, height: 24 };

  it('sits right of the anchor, 8px off it, vertically centred on it', () => {
    expect(placeBeside(rail, label, { width: 1440, height: 900 })).toEqual({ top: 108, left: 56 });
  });

  it('stays 8px above the bottom edge for an anchor at the foot of the screen', () => {
    const foot = { ...rail, top: 880, bottom: 900 };
    expect(placeBeside(foot, label, { width: 1440, height: 900 }).top).toBe(868);
  });

  it('stays 8px inside the top edge', () => {
    const head = { ...rail, top: 0, bottom: 10 };
    expect(placeBeside(head, label, { width: 1440, height: 900 }).top).toBe(8);
  });

  it('shifts left rather than run off a narrow viewport', () => {
    expect(placeBeside(rail, label, { width: 100, height: 900 }).left).toBe(12);
  });
});

describe('Hint hover delay and dismiss() (v247 Decision 6)', () => {
  let fixture: ComponentFixture<DelayHost>;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(DelayHost);
    fixture.detectChanges();
    await fixture.whenStable();
    // Only the delay timer is faked: the open effect's requestAnimationFrame stays real.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });

  afterEach(() => vi.useRealTimers());

  const el = () => fixture.nativeElement as HTMLElement;
  const link = () => el().querySelector('a.link-a') as HTMLAnchorElement;
  const popFor = (hint: string) => el().querySelector(`sb-hint.${hint} [role=tooltip]`) as HTMLElement;
  const trigger = () => el().querySelector('sb-hint.glyph-hint button.trigger') as HTMLButtonElement;
  const isOpen = (hint: string) => popFor(hint).hasAttribute(POPOVER_OPEN_ATTR);
  const fire = (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
  };
  const tick = (ms: number) => {
    vi.advanceTimersByTime(ms);
    fixture.detectChanges();
  };
  const instance = (hint: string): Hint =>
    fixture.debugElement.query(By.css(`sb-hint.${hint}`)).componentInstance as Hint;

  it('exports the 300ms hover delay the rail and the tab bar pass', () => {
    expect(HINT_HOVER_DELAY_MS).toBe(300);
  });

  it('opens an anchor label only once the hover has lasted the delay', () => {
    fire(link(), new MouseEvent('mouseenter'));
    tick(HINT_HOVER_DELAY_MS - 1);
    expect(isOpen('anchored-hint')).toBe(false);
    tick(1);
    expect(isOpen('anchored-hint')).toBe(true);
    fire(link(), new MouseEvent('mouseleave'));
    expect(isOpen('anchored-hint')).toBe(false);
  });

  it('never opens for a pointer that leaves before the delay', () => {
    fire(link(), new MouseEvent('mouseenter'));
    tick(HINT_HOVER_DELAY_MS - 50);
    fire(link(), new MouseEvent('mouseleave'));
    tick(HINT_HOVER_DELAY_MS);
    expect(isOpen('anchored-hint')).toBe(false);
  });

  it('delays hover only: keyboard focus on the anchor opens at once', () => {
    fire(link(), new FocusEvent('focus'));
    expect(isOpen('anchored-hint')).toBe(true);
  });

  it('delays a glyph trigger hover too, but a click pins it at once', () => {
    const host = el().querySelector('sb-hint.glyph-hint')!;
    fire(host, new MouseEvent('mouseenter'));
    expect(isOpen('glyph-hint')).toBe(false);
    fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(isOpen('glyph-hint')).toBe(true);
  });

  it('dismiss() closes a hint held by focus and hover, and cancels a pending hover', () => {
    fire(link(), new FocusEvent('focus'));
    fire(link(), new MouseEvent('mouseenter'));
    tick(HINT_HOVER_DELAY_MS);
    instance('anchored-hint').dismiss();
    fixture.detectChanges();
    expect(isOpen('anchored-hint')).toBe(false);

    fire(link(), new MouseEvent('mouseleave'));
    fire(link(), new FocusEvent('blur'));
    fire(link(), new MouseEvent('mouseenter'));
    instance('anchored-hint').dismiss();
    tick(HINT_HOVER_DELAY_MS * 2);
    expect(isOpen('anchored-hint')).toBe(false);
  });

  it('has no protected close() left: dismiss() is the one way to close', () => {
    expect(SOURCE).not.toMatch(/\bclose\(\): void/);
    expect(SOURCE).not.toMatch(/this\.close\(\)|'close\(\)'/);
    expect(SOURCE).toMatch(/^ {2}dismiss\(\): void \{/m);
  });
});

describe('Hint: one open at a time, app-wide (v247 Decision 7)', () => {
  let fixture: ComponentFixture<PairHost>;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(PairHost);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const popOf = (anchor: Element) =>
    el().querySelector(`[id="${anchor.getAttribute('aria-describedby')}"]`) as HTMLElement;
  const linkA = () => el().querySelector('a.link-a') as HTMLAnchorElement;
  const linkB = () => el().querySelector('a.link-b') as HTMLAnchorElement;
  const glyphPop = () => el().querySelector('sb-hint.glyph-hint [role=tooltip]') as HTMLElement;
  const trigger = () => el().querySelector('sb-hint.glyph-hint button.trigger') as HTMLButtonElement;
  const open = (pop: HTMLElement) => pop.hasAttribute(POPOVER_OPEN_ATTR);
  const fire = async (target: Element, event: Event) => {
    target.dispatchEvent(event);
    fixture.detectChanges();
    await fixture.whenStable();
  };

  it('closes the open label when another label opens', async () => {
    await fire(linkA(), new MouseEvent('mouseenter'));
    expect(open(popOf(linkA()))).toBe(true);
    await fire(linkB(), new FocusEvent('focus'));
    expect(open(popOf(linkB()))).toBe(true);
    expect(open(popOf(linkA()))).toBe(false);
  });

  it('closes an open label when a glyph hint is pinned, and the other way round', async () => {
    await fire(linkA(), new FocusEvent('focus'));
    await fire(trigger(), new MouseEvent('click', { bubbles: true }));
    expect(open(glyphPop())).toBe(true);
    expect(open(popOf(linkA()))).toBe(false);
    await fire(linkB(), new MouseEvent('mouseenter'));
    expect(open(popOf(linkB()))).toBe(true);
    expect(open(glyphPop())).toBe(false);
  });

  it('does not reopen the displaced hint when the newer one closes', async () => {
    await fire(linkA(), new MouseEvent('mouseenter'));
    await fire(linkB(), new MouseEvent('mouseenter'));
    await fire(linkB(), new MouseEvent('mouseleave'));
    expect(open(popOf(linkA()))).toBe(false);
    expect(open(popOf(linkB()))).toBe(false);
  });

  it('frees the slot when an open hint is destroyed', async () => {
    await fire(linkA(), new MouseEvent('mouseenter'));
    fixture.destroy();
    const next = TestBed.createComponent(PairHost);
    next.detectChanges();
    await next.whenStable();
    const link = (next.nativeElement as HTMLElement).querySelector('a.link-b') as HTMLAnchorElement;
    link.dispatchEvent(new MouseEvent('mouseenter'));
    next.detectChanges();
    await next.whenStable();
    const pop = (next.nativeElement as HTMLElement)
      .querySelector(`[id="${link.getAttribute('aria-describedby')}"]`) as HTMLElement;
    expect(open(pop)).toBe(true);
  });
});

describe('Hint.openPinned() and placement (v247)', () => {
  let fixture: ComponentFixture<PinHost>;
  const root = document.documentElement;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(PinHost);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  afterEach(() => {
    // Undo the viewport stub: the own properties shadow Element.prototype's getters.
    delete (root as unknown as Record<string, unknown>)['clientWidth'];
    delete (root as unknown as Record<string, unknown>)['clientHeight'];
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const tab = () => el().querySelector('a.tab') as HTMLAnchorElement;
  const rail = () => el().querySelector('a.rail-link') as HTMLAnchorElement;
  const popOf = (anchor: Element) =>
    el().querySelector(`[id="${anchor.getAttribute('aria-describedby')}"]`) as HTMLElement;
  const open = (anchor: Element) => popOf(anchor).hasAttribute(POPOVER_OPEN_ATTR);
  const settle = async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  };
  const fire = async (target: Element, event: Event) => {
    target.dispatchEvent(event);
    await settle();
  };
  const pin = async () => {
    fixture.componentInstance.tip().openPinned();
    await settle();
  };
  /** jsdom has no layout: give the anchor a rect, the popover a size and the page a viewport. */
  const stubGeometry = (
    anchor: HTMLElement,
    rect: { top: number; bottom: number; left: number; right: number; width: number },
    size: { width: number; height: number },
    viewport: { width: number; height: number },
  ) => {
    anchor.getBoundingClientRect = () =>
      ({ ...rect, x: rect.left, y: rect.top, height: rect.bottom - rect.top, toJSON: () => ({}) }) as DOMRect;
    const pop = popOf(anchor);
    Object.defineProperty(pop, 'offsetWidth', { configurable: true, value: size.width });
    Object.defineProperty(pop, 'offsetHeight', { configurable: true, value: size.height });
    Object.defineProperty(root, 'clientWidth', { configurable: true, value: viewport.width });
    Object.defineProperty(root, 'clientHeight', { configurable: true, value: viewport.height });
  };

  it('opens the label at once, with no hover and no focus', async () => {
    expect(open(tab())).toBe(false);
    await pin();
    expect(open(tab())).toBe(true);
  });

  it('stays open after the hover and the focus that came with the press end', async () => {
    await fire(tab(), new MouseEvent('mouseenter'));
    await fire(tab(), new FocusEvent('focus'));
    await pin();
    await fire(tab(), new MouseEvent('mouseleave'));
    await fire(tab(), new FocusEvent('blur'));
    expect(open(tab())).toBe(true);
  });

  it('survives the long-press order: press, then openPinned(), then the focus the press causes', async () => {
    await fire(tab(), new Event('pointerdown', { bubbles: true }));
    await pin();
    await fire(tab(), new FocusEvent('focus'));
    expect(open(tab())).toBe(true);
  });

  it('closes on the next pointerdown anywhere, the anchor included', async () => {
    await pin();
    await fire(el().querySelector('.outside')!, new MouseEvent('pointerdown', { bubbles: true }));
    expect(open(tab())).toBe(false);
    await pin();
    await fire(tab(), new Event('pointerdown', { bubbles: true }));
    expect(open(tab())).toBe(false);
  });

  it('closes on Escape pressed anywhere in the document, with no focus on it', async () => {
    await pin();
    await fire(document.body, new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(open(tab())).toBe(false);
  });

  it('dismisses the other open hint (one at a time)', async () => {
    await fire(rail(), new FocusEvent('focus'));
    expect(open(rail())).toBe(true);
    await pin();
    expect(open(tab())).toBe(true);
    expect(open(rail())).toBe(false);
  });

  it('places an above label centred over its anchor, 8px off it', async () => {
    stubGeometry(tab(), { top: 788, bottom: 844, left: 78, right: 156, width: 78 },
      { width: 70, height: 24 }, { width: 390, height: 844 });
    await pin();
    expect(popOf(tab()).style.top).toBe('756px');
    expect(popOf(tab()).style.left).toBe('82px');
  });

  it('keeps the default placement beside its anchor', async () => {
    stubGeometry(rail(), { top: 100, bottom: 144, left: 10, right: 54, width: 44 },
      { width: 80, height: 24 }, { width: 1440, height: 900 });
    fixture.componentInstance.railTip().openPinned();
    await settle();
    expect(popOf(rail()).style.top).toBe('110px');
    expect(popOf(rail()).style.left).toBe('62px');
  });
});

describe('placeAbove (v247)', () => {
  const tab = { top: 788, bottom: 844, left: 78, right: 156, width: 78 };
  const label = { width: 70, height: 24 };
  const phone = { width: 390, height: 844 };

  it('sits above the anchor, 8px off it, horizontally centred on it', () => {
    expect(placeAbove(tab, label, phone)).toEqual({ top: 756, left: 82 });
  });

  it('stays 8px inside the left edge for the first tab', () => {
    expect(placeAbove({ ...tab, left: 0, right: 78 }, { width: 100, height: 24 }, phone).left).toBe(8);
  });

  it('stays 8px inside the right edge for the last tab', () => {
    expect(placeAbove({ ...tab, left: 312, right: 390 }, { width: 100, height: 24 }, phone).left).toBe(282);
  });

  it('stays 8px inside the top edge for an anchor at the top of the screen', () => {
    expect(placeAbove({ ...tab, top: 10, bottom: 50 }, label, phone).top).toBe(8);
  });

  it('takes the margin as a parameter', () => {
    expect(placeAbove({ ...tab, left: 0, right: 78 }, { width: 100, height: 24 }, phone, 16).left).toBe(16);
  });
});
