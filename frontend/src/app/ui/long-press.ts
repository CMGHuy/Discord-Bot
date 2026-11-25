import { DestroyRef, Directive, ElementRef, inject, output } from '@angular/core';

/** How long a touch is held before it counts as a press-and-hold (spec v240 section 6). */
export const LONG_PRESS_MS = 500;
/** How far (px, Euclidean) the finger may drift before the hold is a scroll. */
export const LONG_PRESS_SLOP_PX = 10;

/** Pointer types a hold can come from. A mouse has hover instead (spec section 9). */
const PRESS_POINTERS: ReadonlySet<string> = new Set(['touch', 'pen']);

/**
 * Press and hold (v247, spec v240 section 5/6): emits `longPress` when a touch or
 * pen is held on the host for LONG_PRESS_MS without drifting more than
 * LONG_PRESS_SLOP_PX. It emits and does nothing else: the host template wires
 * it, as on the rail and the phone tab bar,
 *
 *   <a ... sbLongPress (longPress)="hint.openPinned()">
 *
 * so the gesture is testable alone and sb-hint keeps owning tooltips.
 *
 * Cancelled by lifting early, pointercancel (the browser took the touch for a
 * scroll), a drift over the slop, a second pointer anywhere, or destroy. The
 * click after a fired press is swallowed in a CAPTURE listener on the host:
 * at the target, capture runs before bubble listeners, so RouterLink never
 * navigates. The swallow clears on that click or the next pointerdown, so a
 * browser that sends no click after a hold never eats a later tap.
 *
 * The OS must not fight it: the host gets class `sb-long-press`, whose global
 * rule (styles.css) turns off the link preview callout and text selection, and
 * a touch-originated contextmenu is prevented. A mouse right-click and the
 * keyboard menu key keep the native menu. pointerdown is never prevented: the
 * rail and the tab bar still scroll, and the anchor still takes focus.
 */
@Directive({
  selector: '[sbLongPress]',
  host: {
    class: 'sb-long-press',
    '(pointerdown)': 'onPointerDown($event)',
    '(pointermove)': 'onPointerMove($event)',
    '(pointerup)': 'cancel()',
    '(pointercancel)': 'cancel()',
    '(contextmenu)': 'onContextMenu($event)',
    '(document:pointerdown)': 'onDocumentPointerDown($event)',
  },
})
export class LongPress {
  readonly longPress = output<void>();

  private timer: ReturnType<typeof setTimeout> | null = null;
  private pointerId: number | null = null;
  private startX = 0;
  private startY = 0;
  private lastPointerType = '';
  private swallowClick = false;

  constructor() {
    const host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
    const onClick = (event: MouseEvent) => this.onClickCapture(event);
    host.addEventListener('click', onClick, true);
    inject(DestroyRef).onDestroy(() => {
      host.removeEventListener('click', onClick, true);
      this.cancel();
    });
  }

  /** The host's own pointerdown. A second pointer while one is held cancels
   *  the press, and does not start a new one. */
  protected onPointerDown(event: PointerEvent): void {
    this.lastPointerType = event.pointerType;
    this.swallowClick = false;
    if (this.timer !== null) {
      this.cancel();
      return;
    }
    if (!PRESS_POINTERS.has(event.pointerType)) return;
    this.pointerId = event.pointerId;
    this.startX = event.clientX;
    this.startY = event.clientY;
    this.timer = setTimeout(() => this.fire(), LONG_PRESS_MS);
  }

  /** A second finger that lands outside the host. The host's own pointerdown
   *  bubbles here after onPointerDown, with the held pointer's id: a no-op. */
  protected onDocumentPointerDown(event: PointerEvent): void {
    if (this.timer !== null && event.pointerId !== this.pointerId) this.cancel();
  }

  protected onPointerMove(event: PointerEvent): void {
    if (this.timer === null || event.pointerId !== this.pointerId) return;
    const drift = Math.hypot(event.clientX - this.startX, event.clientY - this.startY);
    if (drift > LONG_PRESS_SLOP_PX) this.cancel();
  }

  protected onContextMenu(event: MouseEvent): void {
    if (PRESS_POINTERS.has(this.lastPointerType)) event.preventDefault();
  }

  /** Drops a pending press. Never touches swallowClick: the pointerup after a
   *  fired press runs this too, and its click must still be swallowed. */
  protected cancel(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.pointerId = null;
  }

  private fire(): void {
    this.timer = null;
    this.pointerId = null;
    this.swallowClick = true;
    this.longPress.emit();
  }

  private onClickCapture(event: MouseEvent): void {
    if (!this.swallowClick) return;
    this.swallowClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  }
}
