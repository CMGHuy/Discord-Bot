/**
 * Teaches jsdom the Popover API, which it does not implement (spec v194 A1).
 *
 * `sb-hint` shows its popover with `showPopover()` so the browser puts it in
 * the top layer, outside every ancestor's transform, overflow clip and
 * stacking context. jsdom 28 has neither the methods nor the `:popover-open`
 * state, and every `sb-panel` heading renders an `sb-hint`, so any page spec
 * that hovers a heading would throw "showPopover is not a function". That is
 * why this is installed once, globally, from `src/test-setup.ts` -- not per
 * spec the way `installDialogPolyfill()` is.
 *
 * What this stands in for is only the open/closed bookkeeping. jsdom cannot
 * match `:popover-open`, so the state is reflected as the attribute
 * `data-popover-open`, which specs read instead. The top layer, its geometry
 * and the UA display rule are not simulated and must not be asserted
 * against: the layout audit's `hint` check (spec A2) proves those in a real
 * browser.
 *
 * It is deliberately strict, the way engines are: showing an open popover,
 * hiding a closed one, or touching a disconnected one throws
 * `InvalidStateError`, and an element without a `popover` attribute throws
 * `NotSupportedError`. A component that forgets its guards fails its spec
 * here instead of in a user's console.
 *
 * Idempotent, and a no-op in any environment that has the real thing.
 */
export const POPOVER_OPEN_ATTR = 'data-popover-open';

interface PopoverMethods {
  showPopover(): void;
  hidePopover(): void;
  togglePopover(force?: boolean): boolean;
}

function checkPopover(element: HTMLElement): void {
  if (!element.hasAttribute('popover')) throw new DOMException('Not a popover element', 'NotSupportedError');
  if (!element.isConnected) throw new DOMException('Popover is not connected', 'InvalidStateError');
}

export function installPopoverPolyfill(): void {
  const proto = HTMLElement.prototype as unknown as Partial<PopoverMethods>;
  if (typeof proto.showPopover === 'function') return;

  proto.showPopover = function showPopover(this: HTMLElement): void {
    checkPopover(this);
    if (this.hasAttribute(POPOVER_OPEN_ATTR)) throw new DOMException('Popover is already open', 'InvalidStateError');
    this.setAttribute(POPOVER_OPEN_ATTR, '');
  };

  proto.hidePopover = function hidePopover(this: HTMLElement): void {
    checkPopover(this);
    if (!this.hasAttribute(POPOVER_OPEN_ATTR)) throw new DOMException('Popover is not open', 'InvalidStateError');
    this.removeAttribute(POPOVER_OPEN_ATTR);
  };

  proto.togglePopover = function togglePopover(this: HTMLElement, force?: boolean): boolean {
    const open = this.hasAttribute(POPOVER_OPEN_ATTR);
    const want = force ?? !open;
    const methods = this as unknown as PopoverMethods;
    if (want && !open) methods.showPopover();
    else if (!want && open) methods.hidePopover();
    return want;
  };
}
