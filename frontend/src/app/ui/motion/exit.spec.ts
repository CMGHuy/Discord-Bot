import { afterEach, describe, expect, it, vi } from 'vitest';

import { EXIT_FALLBACK_MS, playExit } from './exit';

/* jsdom runs no CSS animation and never fires animationend on its own, so
 * every case dispatches it by hand or lets the fallback timer finish. */
describe('playExit (v168 §3a)', () => {
  afterEach(() => vi.useRealTimers());

  const element = () => document.createElement('div');
  const end = (target: Element) => target.dispatchEvent(new Event('animationend', { bubbles: true }));

  it('finishes at once, adding nothing, when it must not animate', () => {
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-fade-out', false, done);
    expect(done).toHaveBeenCalledTimes(1);
    expect(el.className).toBe('');
  });

  it('plays the class until its own animationend, then removes it and finishes once', () => {
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-fade-out', true, done);
    expect(el.classList).toContain('sb-fade-out');
    expect(done).not.toHaveBeenCalled();
    end(el);
    expect(done).toHaveBeenCalledTimes(1);
    expect(el.classList).not.toContain('sb-fade-out');
    end(el);
    expect(done).toHaveBeenCalledTimes(1);
  });

  it('ignores an animationend bubbling up from a child', () => {
    const el = element();
    const child = el.appendChild(document.createElement('span'));
    const done = vi.fn();
    playExit(el, 'sb-drawer-out', true, done);
    end(child);
    expect(done).not.toHaveBeenCalled();
    expect(el.classList).toContain('sb-drawer-out');
  });

  it('falls back to a timer when animationend never comes', () => {
    vi.useFakeTimers();
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-drawer-out', true, done);
    vi.advanceTimersByTime(EXIT_FALLBACK_MS - 1);
    expect(done).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(done).toHaveBeenCalledTimes(1);
    expect(el.classList).not.toContain('sb-drawer-out');
  });

  it('does not finish twice when the timer fires after animationend', () => {
    vi.useFakeTimers();
    const el = element();
    const done = vi.fn();
    playExit(el, 'sb-fade-out', true, done);
    end(el);
    vi.advanceTimersByTime(EXIT_FALLBACK_MS);
    expect(done).toHaveBeenCalledTimes(1);
  });

  it('cancels without finishing', () => {
    vi.useFakeTimers();
    const el = element();
    const done = vi.fn();
    const cancel = playExit(el, 'sb-fade-out', true, done);
    cancel();
    expect(el.classList).not.toContain('sb-fade-out');
    end(el);
    vi.advanceTimersByTime(EXIT_FALLBACK_MS);
    expect(done).not.toHaveBeenCalled();
  });
});
