import { describe, expect, it } from 'vitest';

import { BREAKPOINTS, viewportFor } from './breakpoints';

/* SR23. The arithmetic is tested at the boundaries and only at the
 * boundaries, because that is the only place it can be wrong: an off-by-one
 * here is invisible until someone resizes to exactly 1024 and a layout picks
 * the wrong branch. */

describe('viewportFor', () => {
  it.each([
    [0, 'xs'],
    [639, 'xs'],
    [640, 'sm'],
    [1023, 'sm'],
    [1024, 'md'],
    [1439, 'md'],
    [1440, 'lg'],
    [1919, 'lg'],
    [1920, 'xl'],
    [3840, 'xl'],
  ])('%ipx is %s', (width, expected) => {
    expect(viewportFor(width)).toBe(expected);
  });

  it('treats each breakpoint as a floor, not a ceiling', () => {
    // min-width semantics: a breakpoint's value is the first width that
    // BELONGS to it. Reading them as ceilings shifts every range by one.
    for (const [name, value] of Object.entries(BREAKPOINTS)) {
      expect(viewportFor(value)).toBe(name);
      expect(viewportFor(value - 1)).not.toBe(name);
    }
  });

  it('publishes the four documented values', () => {
    expect(BREAKPOINTS).toEqual({ sm: 640, md: 1024, lg: 1440, xl: 1920 });
  });
});

// --- SR21: how the automatic state and the explicit toggle compose --------

describe('sidebar state', () => {
  // The rule from spec v18 Decision 8, expressed as the pure function the
  // shell computes with: the viewport FORCES the rail below md, and the
  // user's toggle wins only within a breakpoint. Crossing one re-applies the
  // automatic state, which is why the stored value is a preference rather
  // than the answer.
  const railed = (width: number, userCollapsed: boolean | null) =>
    ['xs', 'sm'].includes(viewportFor(width)) || (userCollapsed ?? false);

  it('is expanded by default on a wide screen', () => {
    expect(railed(1440, null)).toBe(false);
  });

  it('honours an explicit collapse on a wide screen', () => {
    expect(railed(1440, true)).toBe(true);
  });

  it('forces the rail below md whatever the user chose', () => {
    // The preference is not lost -- it simply cannot win here. There is not
    // room for the labels, and letting the stored value through would push
    // the workspace off the screen.
    expect(railed(1023, false)).toBe(true);
    expect(railed(900, false)).toBe(true);
  });

  it('restores the user choice when the window widens again', () => {
    expect(railed(1024, false)).toBe(false);
  });

  it('treats the phone range as narrow too', () => {
    expect(railed(500, false)).toBe(true);
  });
});
