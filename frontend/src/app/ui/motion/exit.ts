/**
 * Longer than every exit in styles/motion.css (200ms), so a missed
 * animationend (a hidden tab, an animation the browser skipped) can never
 * strand an open dialog.
 */
export const EXIT_FALLBACK_MS = 300;

/**
 * Play an exit class on `element`, then call `done` exactly once (spec v168
 * §3a). A `<dialog>`'s close() removes it from rendering at once, so the exit
 * has to run first and the close follow it.
 *
 * - `animate` false (Motion Off or pending): `done()` runs now, nothing is
 *   added, and the returned cancel does nothing.
 * - Otherwise `cls` is added and `done()` runs on the element's OWN
 *   animationend (a child's bubbling one is ignored) or after
 *   EXIT_FALLBACK_MS, whichever is first; `cls` is removed before `done()`.
 *
 * The returned function cancels a running exit: it removes `cls` and `done`
 * never runs.
 */
export function playExit(element: HTMLElement, cls: string, animate: boolean, done: () => void): () => void {
  if (!animate) {
    done();
    return () => undefined;
  }
  let over = false;
  const stop = (): boolean => {
    if (over) return false;
    over = true;
    clearTimeout(timer);
    element.removeEventListener('animationend', onEnd);
    element.classList.remove(cls);
    return true;
  };
  const finish = () => {
    if (stop()) done();
  };
  const onEnd = (event: Event) => {
    if (event.target === element) finish();
  };
  element.classList.add(cls);
  element.addEventListener('animationend', onEnd);
  const timer = setTimeout(finish, EXIT_FALLBACK_MS);
  return () => {
    stop();
  };
}
