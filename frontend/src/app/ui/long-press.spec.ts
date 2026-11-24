import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, RouterLink, provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LONG_PRESS_MS, LONG_PRESS_SLOP_PX, LongPress } from './long-press';

/** A press host: an anchor with no href, so jsdom never tries to navigate. */
@Component({
  imports: [LongPress],
  template: `
    <!-- eslint-disable-next-line @angular-eslint/template/click-events-have-key-events -->
    <a class="target" tabindex="0" sbLongPress (longPress)="presses = presses + 1" (click)="clicks = clicks + 1">
      <span class="icon">i</span>
    </a>
    <span class="outside">Elsewhere</span>
  `,
})
class Host {
  presses = 0;
  clicks = 0;
}

/** The real consumer shape: a routed nav link (rail link, phone tab). */
@Component({
  imports: [LongPress, RouterLink],
  template: `<a routerLink="/trades" class="tab" sbLongPress (longPress)="presses = presses + 1">Trades</a>`,
})
class RouterHost {
  presses = 0;
}

/** jsdom has no PointerEvent: a MouseEvent carrying pointerType and pointerId
 *  is what the directive reads (line-chart.spec.ts does the same). */
function pointer(
  type: string,
  init: { pointerType?: string; pointerId?: number; x?: number; y?: number } = {},
): MouseEvent {
  const event = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    clientX: init.x ?? 100,
    clientY: init.y ?? 100,
  });
  Object.defineProperty(event, 'pointerType', { value: init.pointerType ?? 'touch' });
  Object.defineProperty(event, 'pointerId', { value: init.pointerId ?? 1 });
  return event;
}

const click = () => new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
const contextMenu = () => new MouseEvent('contextmenu', { bubbles: true, cancelable: true });

describe('LongPress (v247)', () => {
  let fixture: ComponentFixture<Host>;

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const target = () => el().querySelector('a.target') as HTMLAnchorElement;
  const presses = () => fixture.componentInstance.presses;
  const clicks = () => fixture.componentInstance.clicks;
  const down = (init: Parameters<typeof pointer>[1] = {}) => target().dispatchEvent(pointer('pointerdown', init));
  /** A held press that fires, then the finger lifting. */
  const hold = () => {
    down();
    vi.advanceTimersByTime(LONG_PRESS_MS);
    target().dispatchEvent(pointer('pointerup'));
  };

  it('pins the gesture constants', () => {
    expect(LONG_PRESS_MS).toBe(500);
    expect(LONG_PRESS_SLOP_PX).toBe(10);
  });

  it('gives its host the sb-long-press class', () => {
    expect(target().classList.contains('sb-long-press')).toBe(true);
  });

  it('fires once at 500ms of a held touch, not before', () => {
    down();
    vi.advanceTimersByTime(LONG_PRESS_MS - 1);
    expect(presses()).toBe(0);
    vi.advanceTimersByTime(1);
    expect(presses()).toBe(1);
    vi.advanceTimersByTime(5 * LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('fires for a pen', () => {
    down({ pointerType: 'pen' });
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('ignores a mouse held down: hover covers mouse', () => {
    down({ pointerType: 'mouse' });
    vi.advanceTimersByTime(2 * LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('is cancelled by lifting the finger before 500ms', () => {
    down();
    vi.advanceTimersByTime(300);
    target().dispatchEvent(pointer('pointerup'));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('is cancelled by pointercancel (the browser took the touch for a scroll)', () => {
    down();
    target().dispatchEvent(pointer('pointercancel'));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('survives a move of exactly 10px', () => {
    down({ x: 100, y: 100 });
    target().dispatchEvent(pointer('pointermove', { x: 106, y: 108 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('is cancelled by a move over 10px', () => {
    down({ x: 100, y: 100 });
    target().dispatchEvent(pointer('pointermove', { x: 100, y: 111 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('ignores the move of another pointer', () => {
    down({ pointerId: 1, x: 100, y: 100 });
    target().dispatchEvent(pointer('pointermove', { pointerId: 7, x: 300, y: 300 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(1);
  });

  it('is cancelled by a second finger on the host', () => {
    down({ pointerId: 1 });
    down({ pointerId: 2 });
    vi.advanceTimersByTime(2 * LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('is cancelled by a second finger anywhere in the document', () => {
    down({ pointerId: 1 });
    el().querySelector('.outside')!.dispatchEvent(pointer('pointerdown', { pointerId: 2 }));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    expect(presses()).toBe(0);
  });

  it('swallows the click that follows a fired press, and only that one', () => {
    hold();
    const first = click();
    target().dispatchEvent(first);
    expect(first.defaultPrevented).toBe(true);
    expect(clicks()).toBe(0);
    target().dispatchEvent(click());
    expect(clicks()).toBe(1);
  });

  it('swallows the click when it lands on a child of the host (the icon)', () => {
    hold();
    el().querySelector('.icon')!.dispatchEvent(click());
    expect(clicks()).toBe(0);
  });

  it('lets a short tap click through', () => {
    down();
    vi.advanceTimersByTime(120);
    target().dispatchEvent(pointer('pointerup'));
    const tap = click();
    target().dispatchEvent(tap);
    expect(tap.defaultPrevented).toBe(false);
    expect(clicks()).toBe(1);
  });

  it('never eats a later tap when the browser sent no click after the hold', () => {
    hold();
    down();
    target().dispatchEvent(pointer('pointerup'));
    target().dispatchEvent(click());
    expect(clicks()).toBe(1);
  });

  it('prevents the context menu of a touch press', () => {
    down();
    const menu = contextMenu();
    target().dispatchEvent(menu);
    expect(menu.defaultPrevented).toBe(true);
  });

  it('keeps the context menu of a mouse right-click', () => {
    down({ pointerType: 'mouse' });
    const menu = contextMenu();
    target().dispatchEvent(menu);
    expect(menu.defaultPrevented).toBe(false);
  });

  it('keeps the context menu with no pointer before it (the keyboard menu key)', () => {
    const menu = contextMenu();
    target().dispatchEvent(menu);
    expect(menu.defaultPrevented).toBe(false);
  });

  it('does not fire after its host is destroyed', () => {
    down();
    fixture.destroy();
    expect(() => vi.advanceTimersByTime(LONG_PRESS_MS)).not.toThrow();
    expect(presses()).toBe(0);
  });
});

describe('LongPress on a routed link (v247)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), provideRouter([])] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const setup = () => {
    const fixture = TestBed.createComponent(RouterHost);
    fixture.detectChanges();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const link = (fixture.nativeElement as HTMLElement).querySelector('a.tab') as HTMLAnchorElement;
    return { fixture, navigate, link };
  };

  it('a plain tap navigates (the control for the next test)', () => {
    const { navigate, link } = setup();
    link.dispatchEvent(click());
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it('a held press emits and navigates nowhere', () => {
    const { fixture, navigate, link } = setup();
    link.dispatchEvent(pointer('pointerdown'));
    vi.advanceTimersByTime(LONG_PRESS_MS);
    link.dispatchEvent(pointer('pointerup'));
    link.dispatchEvent(click());
    expect(fixture.componentInstance.presses).toBe(1);
    expect(navigate).not.toHaveBeenCalled();
  });
});

describe('sb-long-press global rule (v247, spec v240 section 6)', () => {
  // Source text: jsdom computes no -webkit-touch-callout (hit-area.spec.ts reads styles.css the same way).
  const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
  const rule = GLOBAL.match(/^\.sb-long-press\s*\{[^}]*\}/m)?.[0] ?? '';

  it('exists at the top level of styles.css', () => {
    expect(rule).not.toBe('');
  });

  it('turns off the link preview callout', () => {
    expect(rule).toContain('-webkit-touch-callout: none;');
  });

  it('turns off text selection, prefixed and unprefixed', () => {
    expect(rule).toContain('-webkit-user-select: none;');
    expect(rule).toMatch(/(^|\s)user-select: none;/m);
  });
});
