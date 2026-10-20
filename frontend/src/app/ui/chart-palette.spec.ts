import { describe, expect, it } from 'vitest';

import { resolveToken } from './testing/resolve-token';

/** sRGB hex -> OKLab: the space the dataviz palette validator measures in
 *  (spec v80 D2). One metric for every colour gate: under the CIE76 formula
 *  this spec used before, the old pink resistance line sat 15.4 from --neg and
 *  passed, though it reads as a loss (5.9 in OKLab). Thresholds are unchanged. */
function oklab(hex: string): [number, number, number] {
  const to = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  const r = to(parseInt(hex.slice(1, 3), 16) / 255);
  const g = to(parseInt(hex.slice(3, 5), 16) / 255);
  const b = to(parseInt(hex.slice(5, 7), 16) / 255);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

/** OKLab distance x100, the validator's scale. */
function deltaE(a: string, b: string): number {
  const [l1, a1, b1] = oklab(a);
  const [l2, a2, b2] = oklab(b);
  return 100 * Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}

/** OKLCH lightness and chroma, for the validator's band and floor. */
function oklch(hex: string): { l: number; c: number } {
  const [L, A, B] = oklab(hex);
  return { l: L, c: Math.hypot(A, B) };
}

const SERIES = Array.from({ length: 6 }, (_, i) => `--chart-${i + 1}`);

describe('the chart series namespace', () => {
  for (const name of SERIES) {
    it(`defines ${name}`, () => expect(resolveToken(name)).toMatch(/^#[0-9a-f]{6}$/i));
  }

  // G9. Green means gain and red means loss everywhere else in this app; a
  // series that happened to be either would be lying.
  for (const name of SERIES) {
    for (const valence of ['--pos', '--neg']) {
      it(`${name} is not confusable with ${valence}`, () => {
        expect(deltaE(resolveToken(name), resolveToken(valence))).toBeGreaterThan(10);
      });
    }
  }

  it('keeps adjacent series distinguishable at 1px stroke', () => {
    for (let i = 0; i < SERIES.length - 1; i++) {
      expect(deltaE(resolveToken(SERIES[i]), resolveToken(SERIES[i + 1]))).toBeGreaterThan(15);
    }
  });

  // v80 D2. The band and floor the dataviz validator applies for a dark
  // surface. A series outside the band is either too dim to find at 1px or
  // bright enough to read as a highlight; below the chroma floor it reads
  // as grey. Series are no longer pinned to --accent/--info/--warn: C's
  // lavender info fails this floor and its amber fails the band.
  for (const name of SERIES) {
    it(`${name} sits inside the dark-surface lightness band`, () => {
      const { l } = oklch(resolveToken(name));
      expect(l).toBeGreaterThanOrEqual(0.48);
      expect(l).toBeLessThanOrEqual(0.67);
    });

    it(`${name} clears the chroma floor`, () => {
      expect(oklch(resolveToken(name)).c).toBeGreaterThanOrEqual(0.1);
    });
  }
});

/** WCAG 2.1 contrast ratio of two `#rrggbb` colours. */
function ratio(fg: string, bg: string): number {
  const luminance = (hex: string) => {
    const channel = (i: number) => {
      const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
  };
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

/**
 * Spec v167 § 2 and Amendment 6 (new in v167). A series is a 1px line on the
 * chart ground, `--surface` (chart-container.ts; the PNG's CHART_BG), and
 * WCAG 1.4.11 asks 3:1 of a graphical object. The floor is checked on
 * `--surface` only, deliberately: on `--surface-overlay` chart-6 measures
 * 3.94:1, and a series colour there (a tooltip swatch) carries no text.
 * A failure reopens the spec's palette table; it never lowers this number.
 */
describe('the chart series on the chart ground', () => {
  for (const name of SERIES) {
    it(`${name} clears 3:1 on --surface`, () => {
      expect(ratio(resolveToken(name), resolveToken('--surface'))).toBeGreaterThanOrEqual(3);
    });
  }
});
