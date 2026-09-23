import { describe, expect, it } from 'vitest';

import { BREAKPOINTS, Viewport, viewportFor } from './breakpoints';
import { VIEWPORT_ORDER, isInline, rankOf } from './priority';

/* The resolver is pure for the same reason viewportFor is: an off-by-one in
 * the comparison is invisible until someone is at exactly one breakpoint and
 * a column vanishes that should not have. Test the boundaries, and test that
 * the order agrees with the breakpoints rather than restating them. */

describe('VIEWPORT_ORDER', () => {
  it('is every viewport, narrowest first', () => {
    expect(VIEWPORT_ORDER).toEqual(['xs', 'sm', 'md', 'lg', 'xl']);
  });

  it('agrees with viewportFor across the declared breakpoints', () => {
    // The order must be the order viewportFor actually produces as width
    // grows, or `isInline` compares against a scale the app does not use.
    const widths = [0, ...Object.values(BREAKPOINTS)];
    expect(widths.map(viewportFor)).toEqual([...VIEWPORT_ORDER]);
  });
});

describe('rankOf', () => {
  it('ranks ascending from xs', () => {
    expect(VIEWPORT_ORDER.map(rankOf)).toEqual([0, 1, 2, 3, 4]);
  });
});

describe('isInline', () => {
  it('treats an undeclared floor as always inline', () => {
    for (const viewport of VIEWPORT_ORDER) {
      expect(isInline(undefined, viewport)).toBe(true);
    }
  });

  it("inlineFrom 'xs' is inline everywhere", () => {
    for (const viewport of VIEWPORT_ORDER) {
      expect(isInline('xs', viewport)).toBe(true);
    }
  });

  it('is inline at its own floor and above, demoted below', () => {
    const cases: Array<[Viewport, Viewport, boolean]> = [
      ['md', 'xs', false],
      ['md', 'sm', false],
      ['md', 'md', true],
      ['md', 'lg', true],
      ['md', 'xl', true],
    ];
    for (const [floor, viewport, expected] of cases) {
      expect(isInline(floor, viewport)).toBe(expected);
    }
  });

  it('is inline at its own floor for every floor — the boundary case', () => {
    // A floor is inclusive. Reading it as exclusive hides every item at
    // exactly the width it was declared for.
    for (const floor of VIEWPORT_ORDER) {
      expect(isInline(floor, floor)).toBe(true);
    }
  });

  it("inlineFrom 'xl' is demoted at every width but xl", () => {
    expect(VIEWPORT_ORDER.map((v) => isInline('xl', v)))
      .toEqual([false, false, false, false, true]);
  });
});
