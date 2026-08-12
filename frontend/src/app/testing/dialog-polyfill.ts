/**
 * Teaches jsdom the two `<dialog>` methods it does not implement.
 *
 * jsdom 28 gives us the element and its `open` property but not `showModal()`
 * or `close()`, so any component built on a real `<dialog>` throws
 * "showModal is not a function" the moment it is rendered in a test.
 *
 * The alternative was to stop using `<dialog>`, which would be letting the
 * test environment pick the production implementation. `ConfirmDialog` and
 * `Drawer` use it precisely because the browser then owns the top layer, the
 * backdrop, focus trapping, the Escape key and making the background inert —
 * five things a div-plus-overlay has to reimplement and usually gets wrong.
 * Losing all of that to satisfy jsdom would be the wrong trade.
 *
 * What this stands in for is only the open/closed bookkeeping: the attribute
 * flips and `close` fires. Focus trapping and the top layer are not simulated
 * and must not be asserted against — a test that appears to prove focus was
 * trapped here would be proving something about this file instead.
 *
 * Idempotent, and a no-op in any environment that has the real thing.
 */
export function installDialogPolyfill(): void {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & {
    showModal(): void;
    show(): void;
    close(returnValue?: string): void;
  };

  if (typeof proto.showModal === 'function') return;

  proto.showModal = function showModal(this: HTMLDialogElement): void {
    this.setAttribute('open', '');
  };

  proto.show = function show(this: HTMLDialogElement): void {
    this.setAttribute('open', '');
  };

  proto.close = function close(this: HTMLDialogElement, returnValue?: string): void {
    // Closing an already-closed dialog must not fire `close`, or a component
    // that guards its calls would still see a spurious cancellation.
    if (!this.hasAttribute('open')) return;
    this.removeAttribute('open');
    if (returnValue !== undefined) this.returnValue = returnValue;
    this.dispatchEvent(new Event('close'));
  };
}
