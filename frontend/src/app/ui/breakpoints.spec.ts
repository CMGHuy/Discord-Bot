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
