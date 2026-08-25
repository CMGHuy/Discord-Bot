import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function token(name: string): string {
  const m = CSS.match(new RegExp(`^\\s*${name}:\\s*(#[0-9a-fA-F]{6});`, 'm'));
  if (!m) throw new Error(`${name} is not defined as a hex literal`);
  return m[1];
}

/** sRGB hex -> CIE L*a*b* (D65). Enough for a distance check; this is a gate,
 *  not a colour-management pipeline. */
function lab(hex: string): [number, number, number] {
  const to = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const r = to(parseInt(hex.slice(1, 3), 16) / 255);
  const g = to(parseInt(hex.slice(3, 5), 16) / 255);
  const b = to(parseInt(hex.slice(5, 7), 16) / 255);
  const x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047;
  const y = r * 0.2126 + g * 0.7152 + b * 0.0722;
  const z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const [fx, fy, fz] = [f(x), f(y), f(z)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function deltaE(a: string, b: string): number {
  const [l1, a1, b1] = lab(a);
  const [l2, a2, b2] = lab(b);
  return Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}

const SERIES = Array.from({ length: 8 }, (_, i) => `--chart-${i + 1}`);

describe('the chart series namespace', () => {
  for (const name of SERIES) {
    it(`defines ${name}`, () => expect(() => token(name)).not.toThrow());
  }

  // G9. Green means gain and red means loss everywhere else in this app; a
  // series that happened to be either would be lying.
  for (const name of SERIES) {
    for (const valence of ['--pos', '--neg']) {
      it(`${name} is not confusable with ${valence}`, () => {
        expect(deltaE(token(name), token(valence))).toBeGreaterThan(10);
      });
    }
  }

  it('keeps adjacent series distinguishable at 1px stroke', () => {
    for (let i = 0; i < SERIES.length - 1; i++) {
      expect(deltaE(token(SERIES[i]), token(SERIES[i + 1]))).toBeGreaterThan(15);
    }
  });

  // v54 D5: --chart-1/2/3 are supposed to BE --accent/--info/--warn's own
  // hex (tokens.css's own comment says so), kept as a second literal rather
  // than `var(--accent)`. Real browsers DO substitute a nested var() inside
  // a custom property's own value, so aliasing would be safe in production
  // -- it is this repo's OWN test path that isn't: line-chart.ts's
  // seriesColour() reads --chart-* via getComputedStyle().getPropertyValue()
  // under vitest, and jsdom does not perform that substitution (confirmed
  // directly), so an aliased value would reach an SVG stroke as the literal
  // text "var(--accent)". This spec's own token() also requires a literal
  // hex regardless (it parses tokens.css as text). So these stay literal,
  // and this is the loud-failure alternative to aliasing: pin the two
  // copies equal, so a retune of one without the other fails here instead
  // of drifting.
  it('chart-1/2/3 stay equal to the accent/info/warn hex they are meant to be', () => {
    expect(token('--chart-1')).toBe(token('--accent'));
    expect(token('--chart-2')).toBe(token('--info'));
    expect(token('--chart-3')).toBe(token('--warn'));
  });
});
