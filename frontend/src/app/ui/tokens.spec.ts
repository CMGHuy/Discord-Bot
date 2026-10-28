import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { resolveToken } from './testing/resolve-token';
import { allSources, stripComments } from './testing/all-sources';

/**
 * The token file is asserted as TEXT, not through a mounted component.
 *
 * The tokens have to exist whether or not anything consumes them yet — SR2
 * lands the palette before the components that read it — and jsdom does not
 * resolve `var()` chains anyway, so a computed-style assertion here would pass
 * on a stylesheet that defines nothing.
 *
 * **Not `import … from '…tokens.css?raw'`.** That was tried first, to avoid a
 * dependency: Vite honours `?raw`, but the Angular compiler claims every
 * `.css` import ahead of it and hands back a processed style object, so the
 * assertions received an object and failed with a type error rather than a
 * useful message. `@types/node` is types-only and vitest already runs in Node,
 * so reading the file directly is both cheaper and more honest.
 *
 * Resolved from `process.cwd()`, not from `import.meta.url`. Under
 * `@angular/build:unit-test` the module's own URL is an `http:` one — the
 * builder serves the bundle rather than loading it off disk — and `readFileSync`
 * rejects it with "The URL must be of scheme file". `ng test` always runs with
 * the frontend project root as its working directory.
 */
const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');
/** Tier 3 is the LAST top-level block of tokens.css, under this banner (spec v167 §3). */
const TIER3_BANNER = '/* ===== Tier 3: component tokens (spec v167 §3) ===== */';
/** Everything from the tier-3 banner to the end of the file; '' while the banner is missing. */
const TIER3 = CSS.includes(TIER3_BANNER) ? CSS.slice(CSS.indexOf(TIER3_BANNER)) : '';

const REQUIRED = [
  '--bg',
  '--surface',
  '--surface-raised',
  '--surface-overlay',
  '--border',
  '--border-strong',
  '--scrim',

  '--text',
  '--text-secondary',
  '--text-muted',
  '--text-faint',

  '--pos',
  '--neg',
  '--warn',
  '--accent',
  '--accent-fill',
  '--accent-fill-hi',
  '--on-accent',
  '--info',

  '--pos-soft',
  '--neg-soft',
  '--warn-soft',
  '--accent-soft',
  '--info-soft',

  '--quality-1',
  '--quality-2',
  '--quality-3',
  '--quality-4',
  '--quality-5',

  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
  '--chart-6',

  '--dur-instant',
  '--dur-base',
  '--dur-slow',
  '--ease-out',
  '--ease-spring',

  '--control-h',
  '--section-gap',

  // v167 §3, tier 3
  '--panel-radius',
  '--control-radius',
  '--chip-radius',
  '--radius-sm',
  '--panel-bg',
  '--panel-border',
  '--panel-shadow',
  '--panel-inner-bg',
  '--panel-inner-radius',
  '--shadow-overlay',
  '--btn-fill',
  '--btn-fill-hover',
  '--scrim-soft',

  // v168 §1, motion (tier 3); v195 §1.2 deleted --dur-enter and --panel-shadow-lift
  '--motion-scale',
  '--dur-count',
  '--dur-draw',
  '--flash-up-text',
  '--flash-down-text',
  // v195 §1.2: the one UI transition duration (tier 2)
  '--dur-ui',
];

describe('design tokens', () => {
  for (const name of REQUIRED) {
    it(`defines ${name}`, () => {
      expect(CSS).toMatch(new RegExp(`^\\s*${name}:`, 'm'));
    });
  }

  it('sizes controls with a single height token', () => {
    expect(CSS).toMatch(/^\s*--control-h:\s*28px;/m);
  });

  /* Inverted by v168 (spec D2): the OS reduced-motion setting is ignored by
   * design, and the shell's Motion control drives data-motion instead. The
   * media-feature name must not come back into this file, comments included. */
  it('ignores the OS reduced-motion setting: no media block; motion.css carries the Off rules', () => {
    expect(CSS).not.toContain('prefers-reduced-motion');
    const motion = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8');
    expect(motion).toMatch(/\[data-motion="?off"?\]\s*\{\s*--motion-scale:\s*0;\s*\}/);
  });

  it('has dropped --space-28', () => {
    expect(CSS).not.toMatch(/^\s*--space-28:/m);
  });

  it('has dropped the old greyscale quality tokens', () => {
    for (const dead of ['--quality-high', '--quality-mid', '--quality-low']) {
      expect(CSS).not.toMatch(new RegExp(`^\\s*${dead}:`, 'm'));
    }
  });

  it('has dropped --chart-7 and --chart-8 (v80 D2: six series)', () => {
    expect(CSS).not.toMatch(/^\s*--chart-7:/m);
    expect(CSS).not.toMatch(/^\s*--chart-8:/m);
  });

  it('keeps the complete six-colour categorical chart palette', () => {
    const chartTokens = [...CSS.matchAll(/^\s*--chart-(\d):\s*#[0-9a-f]{6};/gim)]
      .map((match) => Number(match[1]));
    expect(chartTokens).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('keeps --transition as an alias so existing call sites still compile', () => {
    expect(CSS).toMatch(/^\s*--transition:/m);
  });

  /* v167 §3 supersedes v54 D2's one-shadow law: two levels, both in tier 3. */
  it('defines the two elevation shadows', () => {
    expect(TIER3).toMatch(/^\s*--panel-shadow:\s*none;/m);
    expect(TIER3).toMatch(/^\s*--shadow-overlay:\s*0 16px 40px rgba\(0, 0, 0, \.55\), 0 2px 8px rgba\(0, 0, 0, \.4\);/m);
    // declared once, in tier 3 -- not left behind in tier 2 as well
    expect([...CSS.matchAll(/^\s*--shadow-overlay:/gm)]).toHaveLength(1);
  });
});

const UI = join(process.cwd(), 'src/app/ui');

describe('control height', () => {
  for (const file of ['form-controls.ts', 'button.ts']) {
    it(`${file} sizes its controls from --control-h`, () => {
      const source = readFileSync(join(UI, file), 'utf8');
      expect(source).toContain('var(--control-h)');
    });
  }

  it('no control hardcodes a vertical padding any more', () => {
    const source = readFileSync(join(UI, 'form-controls.ts'), 'utf8');
    expect(source).not.toMatch(/padding:\s*var\(--space-4\)\s+var\(--space-8\)/);
  });
});

const WORKSPACES = join(process.cwd(), 'src/app/workspaces');

function workspaceSources(): { name: string; source: string }[] {
  const out: { name: string; source: string }[] = [];
  // withFileTypes + isDirectory: v85's workspace-consistency.spec.ts lives
  // directly under workspaces/, not inside a per-workspace subdirectory --
  // a bare readdirSync(dir) here throws ENOTDIR on it.
  for (const dir of readdirSync(WORKSPACES, { withFileTypes: true })) {
    if (!dir.isDirectory()) continue;
    for (const file of readdirSync(join(WORKSPACES, dir.name))) {
      if (!file.endsWith('.ts') || file.endsWith('.spec.ts')) continue;
      out.push({
        name: `${dir.name}/${file}`,
        source: readFileSync(join(WORKSPACES, dir.name, file), 'utf8'),
      });
    }
  }
  return out;
}

const CONTROLS = /sb-button|sb-select|sb-text-input|sb-checkbox|sb-filter-bar/;

/**
 * Rows that align by hand and are RIGHT to.
 *
 * Exact names, not prefixes: a prefix list would exempt `head-actions` under
 * `head`, and `head-actions` is a genuine control row (it is converted).
 * Every entry below is a row that is not a row of controls, or one whose
 * layout would regress if it were bottom-aligned. Adding a name here is a
 * claim about the row, so it needs a reason on the line.
 */
const NOT_CONTROL_ROWS = new Set([
  // Text and figures. Baseline or centre on running text is correct.
  'head', 'meta', 'cell', 'count', 'figures', 'tags',
  'jobhead', // a chip beside a timestamp
  'leg', // v194 B3: a "Leg N of M" label beside its info glyph -- text, not controls
  // The calendar's month stepper: two buttons with the month LABEL
  // between them. The row sits inside an sb-control-row already; its
  // middle child is running text, and bottom-aligning that text
  // against two buttons is the regression, not the fix.
  'months',
  // Versions' release-lane row: a component-name label beside a bar-chart
  // strip of absolutely-positioned segment bars (v54's segment variant,
  // for their paint only). It reads as data visualisation, not a row of
  // controls to bottom-align -- flagged only because the strip's segments
  // happen to be sb-button underneath.
  'lane',
  // The Dashboard's two remaining data-card rows (five metric cards, the
  // lifecycle strip) -- rows of DISPLAYED figures, not controls, so
  // sb-control-row's bottom-alignment answer does not apply. Flex here is
  // what lets a card size to its own content (a long label) while still
  // filling the row, and align-items: stretch is what makes every card in
  // the row match its tallest sibling -- both are the point, not a stand-in
  // for sb-control-row. The third, the metric-chip row, is sb-chip-row now
  // (v54 Task 8) -- a component, not a hand-rolled class this gate can see.
  'primary', 'lifecycle',
  // The plan-lifecycle diagram + its legend, centred as one figure beside
  // the paragraph it illustrates -- not a row of controls either.
  'lifecycle-figure',
  'chip', // the inside of a bordered chip, not a row of controls
  'scan', // the scan-duration figures beside their sparkline
  // Risk's heat gauge beside its cap/used/remaining readout (v85 D36) --
  // same category as 'scan' above: a figure and the numbers explaining it,
  // not a row of controls to bottom-align.
  'gauge-budget',
  // Trade Detail's ticker/status title is a semantic heading, not a control
  // lane. It is the one flex row whose children are data and status only.
  'trade-title',
  // v166: the Trade Detail identity row (title, tags, id) is data and status
  // chips, and the Back link is a navigation anchor, not a control lane.
  'identity', 'back',
  // Analytics' win/loss donut beside its avg-win/avg-loss captions (v85
  // D39) -- same category again: a figure and the numbers explaining it.
  'winloss',
  'command-error', // <p role="alert">: message text with a dismiss affordance
  'triage', // groups the two <label> rows below; owns neither control
  // <label> elements. Converting one to a component host would break the
  // implicit association that makes clicking the text focus the control.
  'level', 'import-file',
  // The killswitch row: a multi-paragraph block beside one button, held by
  // align-items: flex-start and justify-content: space-between, collapsing at
  // 720px rather than the primitive's 640. Bottom-aligning the button against
  // a variable-height paragraph is a regression, not the fix.
  'kill',
]);

describe('no workspace hand-rolls a control row', () => {
  for (const { name, source } of workspaceSources()) {
    if (!CONTROLS.test(source)) continue;

    it(`${name} routes its control rows through sb-control-row`, () => {
      // Every flex rule that also declares an alignment is a row that took a
      // position on the question sb-control-row exists to answer.
      const offenders = [...source.matchAll(/\.([\w-]+)\s*\{[^}]*display:\s*flex[^}]*\}/g)]
        .filter(([rule]) => /align-items:\s*(center|flex-start|stretch)/.test(rule))
        .map(([, className]) => className)
        .filter((className) => !NOT_CONTROL_ROWS.has(className));

      expect(offenders).toEqual([]);
    });
  }
});

/**
 * v195 §1.1: the Graphite palette (supersedes v167 §2's Arctic Navy). Tier 2
 * holds no colour, it references a tier-1 palette entry in styles/palette.css.
 * Two assertions per token -- the reference as written (the tier contract) and
 * the value it resolves to (the spec's table) -- so a palette edit that keeps
 * the names but drifts a value fails here as well as in contrast.spec.ts.
 */
describe('v195 §1.1: the Graphite palette', () => {
  const EXPECTED: [token: string, palette: string, value: string][] = [
    ['--bg', '--graphite-950', '#0d0f12'],
    ['--surface', '--graphite-900', '#15181d'],
    ['--surface-raised', '--graphite-850', '#1c2128'],
    ['--surface-overlay', '--graphite-800', '#1f242b'],
    ['--overlay-dim', '--graphite-950-a72', 'rgba(13, 15, 18, 0.72)'],
    ['--border', '--graphite-750', '#23272e'],
    ['--border-strong', '--graphite-700', '#2d333b'],
    ['--text', '--grey-100', '#e6e8eb'],
    ['--text-secondary', '--grey-300', '#c9d1d9'],
    ['--text-muted', '--grey-400', '#9aa4b2'],
    ['--text-faint', '--graphite-500', '#6b7280'],
    ['--accent', '--steel-400', '#6ea8fe'],
    ['--accent-fill', '--steel-600', '#2563c4'],
    ['--accent-fill-hi', '--steel-500', '#2d6cd3'],
    ['--on-accent', '--white', '#ffffff'],
    ['--pos', '--green-500', '#3fb68b'],
    // Spec table said #e5534b; amended to #f06e66 for WCAG AA on the raised
    // and overlay surfaces and on its own tint (V195-2).
    ['--neg', '--red-500', '#f06e66'],
    ['--warn', '--amber-500', '#d29922'],
    // Spec table said #b392f0; amended to #c193ed to clear OKLab dE 10 from
    // the accent entry line in the Discord image (V195-2).
    ['--info', '--violet-400', '#c193ed'],
    ['--pos-soft', '--green-500-a12', 'rgba(63, 182, 139, 0.12)'],
    ['--neg-soft', '--red-500-a12', 'rgba(240, 110, 102, 0.12)'],
    ['--warn-soft', '--amber-500-a12', 'rgba(210, 153, 34, 0.12)'],
    ['--accent-soft', '--steel-400-a18', 'rgba(110, 168, 254, 0.18)'],
    ['--info-soft', '--violet-400-a14', 'rgba(193, 147, 237, 0.14)'],
  ];

  for (const [name, palette, value] of EXPECTED) {
    it(`${name} references ${palette}`, () => {
      expect(CSS).toMatch(new RegExp(`^\\s*${name}:\\s*var\\(${palette}\\);`, 'm'));
    });

    it(`${name} resolves to ${value}`, () => {
      expect(resolveToken(name)).toBe(value);
    });
  }

  it('leaves --quality-4 and the six chart series literal (spec §1 exception)', () => {
    expect(CSS).toMatch(/^\s*--quality-4:\s*#9acd32;/m);
    for (let i = 1; i <= 6; i++) {
      expect(CSS).toMatch(new RegExp(`^\\s*--chart-${i}:\\s*#[0-9a-f]{6};`, 'mi'));
    }
  });

  /* #c97a22 sat OKLab dE 8.0 from the new --warn, and the Discord price pane
   * draws current price (warn) beside the strategy target line (chart-2). */
  it('re-derives --chart-2 off the amber warn for the Graphite ground', () => {
    expect(resolveToken('--chart-2')).toBe('#bd6c18');
  });

  it('keeps no Arctic Navy palette name in either token file', () => {
    const PALETTE = readFileSync(join(process.cwd(), 'src/styles/palette.css'), 'utf8');
    for (const source of [CSS, PALETTE]) {
      expect(source).not.toMatch(/--(?:navy|slate|sky|teal)-\d/);
    }
  });
});

describe('v80 D3: type, shape and touch', () => {
  it('sets the headline figure to 28px', () => {
    expect(CSS).toMatch(/^\s*--text-metric:\s*calc\(28px \* var\(--text-scale\)\);/m);
  });

  it('offers a hero size above the primary metric size', () => {
    const style = getComputedStyle(document.documentElement);
    expect(style.getPropertyValue('--text-hero').trim()).not.toBe('');
    // Same calc(px * var(--text-scale)) shape as every other size token, so
    // the zoom control reaches it too. Asserted on the source: the jsdom
    // document carries flattened literals (spec v167, Amendment 1), where
    // var(--text-scale) has already been replaced by its value.
    expect(CSS).toMatch(/^\s*--text-hero:\s*calc\(44px \* var\(--text-scale\)\);/m);
  });

  /* v167 §3 supersedes v80 D3's single 2px: four targets, all in tier 3,
   * and the two old tokens are gone so no unclassified corner survives.
   * v195 §1.5: 6px panels, 4px controls and chips, 2px cells. */
  it('defines the four radius targets', () => {
    expect(TIER3).toMatch(/^\s*--panel-radius:\s*6px;/m);
    expect(TIER3).toMatch(/^\s*--control-radius:\s*4px;/m);
    expect(TIER3).toMatch(/^\s*--chip-radius:\s*4px;/m);
    expect(TIER3).toMatch(/^\s*--radius-sm:\s*2px;/m);
    expect(CSS).not.toMatch(/^\s*--radius(?:-chip)?:/m);
  });

  it('defines one row height and one form-control text size', () => {
    expect(CSS).toMatch(/^\s*--row-h:\s*32px;/m);
    expect(CSS).toMatch(/^\s*--text-control:\s*calc\(14px \* var\(--text-scale\)\);/m);
  });

  it('grows controls, rows, control text and the hit area on phone and tablet (v179 §3.4)', () => {
    const block = CSS.match(/@media \(pointer: coarse\), \(max-width: 1023px\)\s*\{([\s\S]*?)\n\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/--control-h:\s*44px;/);
    expect(block![1]).toMatch(/--row-h:\s*44px;/);
    expect(block![1]).toMatch(/--text-control:\s*calc\(16px \* var\(--text-scale\)\);/);
    expect(block![1]).toMatch(/--hit-min:\s*44px;/);
  });
});

/**
 * v167 §3: the component tokens. Values are asserted as DECLARED (whitespace
 * collapsed), because tier 3 is the contract components read; one resolved
 * case proves the gradient reaches the Graphite fill blues through tier 2.
 */
describe('v167 §3: the tier-3 component tokens', () => {
  const declared = (name: string) =>
    TIER3.match(new RegExp(`^\\s*${name}:\\s*([^;]+);`, 'm'))?.[1].replace(/\s+/g, ' ').trim();

  const VALUES: Record<string, string> = {
    '--panel-radius': '6px',
    '--control-radius': '4px',
    '--chip-radius': '4px',
    '--radius-sm': '2px',
    '--panel-bg': 'var(--surface)',
    '--panel-border': '1px solid var(--border)',
    '--panel-shadow': 'none',
    '--panel-inner-bg': 'var(--surface-raised)',
    '--panel-inner-radius': 'var(--control-radius)',
    '--shadow-overlay': '0 16px 40px rgba(0, 0, 0, .55), 0 2px 8px rgba(0, 0, 0, .4)',
    '--btn-fill': 'var(--accent-fill)',
    '--btn-fill-hover': 'var(--accent-fill-hi)',
    '--scrim-soft': 'rgb(0 0 0 / 0.5)',
  };

  it('sits in one :root block after every other block, under its banner', () => {
    expect(TIER3).not.toBe('');
    expect(TIER3.match(/:root\s*\{/g)).toHaveLength(1);
    expect(TIER3).not.toContain('@media');
  });

  for (const [name, value] of Object.entries(VALUES)) {
    it(`${name} is ${value}`, () => {
      expect(declared(name)).toBe(value);
    });
  }

  /* v195 §1.2: the primary button is one flat fill, no gradient. */
  it('resolves the flat button fill to the two Graphite fill blues', () => {
    expect(resolveToken('--btn-fill')).toBe('#2563c4');
    expect(resolveToken('--btn-fill-hover')).toBe('#2d6cd3');
  });

  /* A gradient is an image: as background-color it is invalid and the
   * declaration is dropped silently, leaving the element transparent. */
  it('never paints a gradient token as background-color (styles.css and ui/)', () => {
    const GRADIENT_AS_COLOUR = /background-color:\s*var\(--(?:panel-bg|btn-fill|btn-fill-hover)\)/;
    const files = [
      join(process.cwd(), 'src/styles.css'),
      ...readdirSync(UI)
        .filter((file) => file.endsWith('.ts') && !file.endsWith('.spec.ts'))
        .map((file) => join(UI, file)),
    ];
    const offenders = files.filter((file) => GRADIENT_AS_COLOUR.test(readFileSync(file, 'utf8')));
    expect(offenders).toEqual([]);
  });
});

/**
 * v168 §1: every duration is a calc() over --motion-scale, so one declaration
 * in styles/motion.css ([data-motion=off] { --motion-scale: 0; }) zeroes them
 * all. The scale's default and every new v168 token sit INSIDE v167's tier-3
 * block (spec v168 amendment 9): dump_tokens.py and resolve-token.ts read
 * every top-level :root, and motion.css is outside both, so the default must
 * live here. Reduced is not a multiplier (spec §1): the scale is only ever 1
 * or 0.
 */
describe('v168 §1: motion tokens', () => {
  const declared = (source: string, name: string) =>
    source.match(new RegExp(`^\\s*${name}:\\s*([^;]+);`, 'm'))?.[1].replace(/\s+/g, ' ').trim();

  const DURATIONS: Record<string, string> = {
    '--dur-instant': '90ms',
    '--dur-ui': '120ms',
    '--dur-base': '160ms',
    '--dur-slow': '260ms',
    '--dur-count': '900ms',
    '--dur-draw': '1200ms',
  };

  it('scales every duration by --motion-scale', () => {
    for (const [name, ms] of Object.entries(DURATIONS)) {
      expect(declared(CSS, name), name).toBe(`calc(${ms} * var(--motion-scale))`);
    }
  });

  it('declares the scale once, as 1, in tier 3', () => {
    expect(declared(TIER3, '--motion-scale')).toBe('1');
    expect([...CSS.matchAll(/^\s*--motion-scale:/gm)]).toHaveLength(1);
  });

  it('puts every new v168 token inside the tier-3 block', () => {
    const NEW = ['--dur-count', '--dur-draw', '--flash-up-text', '--flash-down-text'];
    for (const name of NEW) {
      expect(TIER3, name).toMatch(new RegExp(`^\\s*${name}:`, 'm'));
      expect([...CSS.matchAll(new RegExp(`^\\s*${name}:`, 'gm'))], name).toHaveLength(1);
    }
  });

  it('keeps both easings exactly as they were', () => {
    expect(declared(CSS, '--ease-out')).toBe('cubic-bezier(0.2, 0.8, 0.3, 1)');
    expect(declared(CSS, '--ease-spring')).toBe('cubic-bezier(0.34, 1.4, 0.64, 1)');
  });

  it('gives the flash text its spec values', () => {
    expect(declared(TIER3, '--flash-up-text')).toBe('var(--pos)');
    expect(declared(TIER3, '--flash-down-text')).toBe('var(--neg)');
  });

  it('reaches jsdom with the scale already resolved', () => {
    expect(resolveToken('--dur-base')).toBe('calc(160ms * 1)');
    expect(resolveToken('--motion-scale')).toBe('1');
  });
});

/**
 * v179 §3.4 / §6b.6, raised by v195 §1.3 (correction 12): the smallest two
 * size tokens, micro and chip, are 12px and floored there inside the token,
 * as max(12px, ...), so the 90% zoom preference (shell.ts ZOOM_CHOICES)
 * cannot push them below it. Every other size token scales freely: at 90%
 * --text-table is 11.7px, which stays above the 11px rendered floor the
 * layout audit measures (MIN_TEXT_PX).
 */
describe('v195: the 12px micro and chip floor', () => {
  /** Every size token: a --text-* declaration whose value reads --text-scale
   *  (the colour tokens --text-muted/--text-secondary/... never do). */
  const SIZE = /^\s*(--text-[a-z]+):\s*(.*var\(--text-scale\).*);/gm;
  const sizes = [...CSS.matchAll(SIZE)].map((m) => ({ name: m[1], value: m[2].trim() }));

  /** Pixels at `scale` for `calc(Npx * var(--text-scale))`, optionally
   *  wrapped in `max(Fpx, ...)`. */
  function px(value: string, scale: number): number {
    const base = Number(value.match(/calc\((\d+(?:\.\d+)?)px \* var\(--text-scale\)\)/)![1]) * scale;
    const floor = value.match(/^max\((\d+)px,/);
    return floor ? Math.max(Number(floor[1]), base) : base;
  }

  const sizeOf = (name: string, scale: number) => px(sizes.find((s) => s.name === name)!.value, scale);

  it('finds the size tokens', () => {
    expect(sizes.map((s) => s.name)).toEqual(expect.arrayContaining(['--text-micro', '--text-chip', '--text-table']));
  });

  it.each([1, 1.1, 1.25])('keeps every size token at or above 12px at scale %s', (scale) => {
    const below = sizes
      .filter((s) => px(s.value, scale) < 12)
      .map((s) => `${s.name}=${px(s.value, scale)}px`);
    expect(below).toEqual([]);
  });

  it('keeps micro and chip at 12px and every other token at or above 11px at the 90% step', () => {
    expect(sizeOf('--text-micro', 0.9)).toBe(12);
    expect(sizeOf('--text-chip', 0.9)).toBe(12);
    const below = sizes
      .filter((s) => px(s.value, 0.9) < 11)
      .map((s) => `${s.name}=${px(s.value, 0.9)}px`);
    expect(below).toEqual([]);
  });

  it('floors the two smallest tokens at 12px, inside the token', () => {
    expect(CSS).toMatch(/^\s*--text-micro:\s*max\(12px, calc\(12px \* var\(--text-scale\)\)\);/m);
    expect(CSS).toMatch(/^\s*--text-chip:\s*max\(12px, calc\(12px \* var\(--text-scale\)\)\);/m);
  });

  it('still grows a floored token above 100%', () => {
    expect(sizeOf('--text-micro', 1.25)).toBeCloseTo(15);
  });

  it('reaches jsdom through the regenerated fixture', () => {
    expect(resolveToken('--text-micro')).toBe('max(12px, calc(12px * 1))');
    expect(resolveToken('--text-chip')).toBe('max(12px, calc(12px * 1))');
  });
});

/** v179 §3.3: every numeric value uses one tabular face, named once. */
describe('v179: one numeric face', () => {
  it('declares --font-num as the mono family', () => {
    expect(CSS).toMatch(/^\s*--font-num:\s*var\(--font-mono\);/m);
    expect(resolveToken('--font-num')).toBe(resolveToken('--font-mono'));
  });
});

/**
 * v186 D4: one face for DISPLAY figures, named by role beside --font-num.
 * Tier 2 (a system role), so it sits in the first :root block, before the
 * tier-3 banner. --font-num stays mono: columns still align.
 */
describe('v186: the display-figure tokens', () => {
  const TIER2 = TIER3 ? CSS.slice(0, CSS.indexOf(TIER3_BANNER)) : CSS;
  const FIGURE: Record<string, string> = {
    '--font-figure': 'var(--font-sans)',
    '--figure-weight': '600',
    '--figure-tracking': '-0.02em',
  };
  const declaredIn = (source: string, name: string) =>
    source.match(new RegExp(`^\\s*${name}:\\s*([^;]+);`, 'm'))?.[1].trim();
  const at = (name: string) => CSS.search(new RegExp(`^\\s*${name}:`, 'm'));

  it('declares the figure face, weight and tracking in tier 2', () => {
    for (const [name, value] of Object.entries(FIGURE)) {
      expect(declaredIn(TIER2, name), name).toBe(value);
    }
  });

  it('declares each exactly once, never in tier 3', () => {
    for (const name of Object.keys(FIGURE)) {
      expect([...CSS.matchAll(new RegExp(`^\\s*${name}:`, 'gm'))], name).toHaveLength(1);
      expect(declaredIn(TIER3, name), name).toBeUndefined();
    }
  });

  it('places them straight after --font-num, in order', () => {
    expect(at('--font-num')).toBeGreaterThan(-1);
    expect(at('--font-num')).toBeLessThan(at('--font-figure'));
    expect(at('--font-figure')).toBeLessThan(at('--figure-weight'));
    expect(at('--figure-weight')).toBeLessThan(at('--figure-tracking'));
  });

  it('leaves --font-num on the mono family', () => {
    expect(CSS).toMatch(/^\s*--font-num:\s*var\(--font-mono\);/m);
  });

  it('reaches jsdom through the regenerated fixture', () => {
    expect(resolveToken('--font-figure')).toBe(resolveToken('--font-sans'));
    expect(resolveToken('--figure-weight')).toBe('600');
    expect(resolveToken('--figure-tracking')).toBe('-0.02em');
  });
});

/**
 * v195 §1.2: decoration removed. The four tokens only decoration read are
 * gone from tokens.css and from every reader (components, styles.css,
 * motion.css), and a UI transition is one 120ms step, read through the
 * --transition alias every existing call site already uses.
 */
describe('v195 §1.2: decoration tokens deleted, 120ms transitions', () => {
  const MOTION_CSS = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8');
  const DELETED = ['--glow-ambient', '--glow-accent', '--panel-shadow-lift', '--dur-enter'];

  it.each(DELETED)('declares no %s', (name) => {
    expect(CSS).not.toMatch(new RegExp(`^\\s*${name}:`, 'm'));
  });

  it.each(DELETED)('leaves no reader or setter of %s', (name) => {
    const holders = [
      ...allSources(),
      { name: 'styles/motion.css', source: MOTION_CSS },
      { name: 'styles/tokens.css', source: CSS },
    ]
      .filter(({ source }) => stripComments(source).includes(name))
      .map(({ name: file }) => file);
    expect(holders).toEqual([]);
  });

  it('times every UI transition at 120ms through --transition', () => {
    expect(CSS).toMatch(/^\s*--dur-ui:\s*calc\(120ms \* var\(--motion-scale\)\);/m);
    expect(CSS).toMatch(/^\s*--transition:\s*var\(--dur-ui\) var\(--ease-out\);/m);
    expect(resolveToken('--dur-ui')).toBe('calc(120ms * 1)');
  });
});
