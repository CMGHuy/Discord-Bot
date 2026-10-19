import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * styles/motion.css (spec v168 §1-§3), asserted as SOURCE TEXT. jsdom sees
 * flattened tokens and no @media (v167), so a computed-style read would
 * prove nothing; behaviour is asserted elsewhere through classes, attributes
 * and the MotionStarts log. Read with readFileSync from process.cwd(), never
 * `?raw` (tokens.spec.ts records why).
 */
const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
const uncomment = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '');
const MOTION = uncomment(read('src/styles/motion.css'));
const STYLES = uncomment(read('src/styles.css'));

/** The body of the block whose `{` is the first one at or after `from`, braces matched. */
function bodyAt(css: string, from: number): string {
  const open = css.indexOf('{', from);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    if (css[i] === '}' && --depth === 0) return css.slice(open + 1, i);
  }
  return css.slice(open + 1);
}

/** The bodies of every block opened by `header` (e.g. one media query), joined. */
function blocksOf(css: string, header: string): string {
  const found: string[] = [];
  for (let at = css.indexOf(header); at !== -1; at = css.indexOf(header, at + header.length)) {
    found.push(bodyAt(css, at));
  }
  return found.join('\n');
}

/** Every innermost rule, selector and body whitespace-collapsed. */
function rules(css: string): { selector: string; body: string }[] {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, selector, body]) => ({
    selector: selector.replace(/\s+/g, ' ').trim(),
    body: body.replace(/\s+/g, ' ').trim(),
  }));
}

/** A selector list split on its top-level commas, not those inside `:is(…)`. */
function splitList(list: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < list.length; i++) {
    if (list[i] === '(') depth++;
    if (list[i] === ')') depth--;
    if (list[i] === ',' && depth === 0) {
      parts.push(list.slice(start, i).trim());
      start = i + 1;
    }
  }
  parts.push(list.slice(start).trim());
  return parts;
}

/** The bodies of the rules whose selector list contains `selector` verbatim. */
function bodiesFor(css: string, selector: string): string[] {
  return rules(css)
    .filter(({ selector: list }) => splitList(list).includes(selector))
    .map(({ body }) => body);
}

/** Every `@keyframes name { … }`, in source order. */
function keyframeList(css: string): [string, string][] {
  return [...css.matchAll(/@keyframes\s+([\w-]+)\s*\{/g)].map((match) => [
    match[1],
    bodyAt(css, match.index!).replace(/\s+/g, ' ').trim(),
  ]);
}

const KEYFRAMES = [
  // moved (v168 §2, amendment 7)
  'sb-pulse-soft', 'sb-pulse-dim', 'sb-pulse-blink', 'sb-spin', 'sb-route-spin', 'sb-scan-sweep',
  'sb-scan-strip-in', 'sb-flash-up', 'sb-flash-down', 'sb-row-blink', 'sb-tape-slide',
  // new (v168 §3)
  'sb-enter', 'sb-fade-in', 'sb-pop-in', 'sb-drawer-in', 'sb-drawer-out', 'sb-sheet-in', 'sb-sheet-out',
  'sb-fade-out', 'sb-ping', 'sb-shimmer', 'sb-draw-inset', 'sb-draw-circle', 'sb-ambient-drift',
];
const NEW_KEYFRAMES = KEYFRAMES.slice(KEYFRAMES.indexOf('sb-enter'));
const COMPOSITOR = new Set(['transform', 'opacity', 'filter', 'clip-path', 'background-position']);
const STAGGER = '.sb-entering > * > :is(.sb-stack, .sb-row, sb-panel-grid, .sb-stagger) > ';
const ENTRANCES = ['.sb-enter', '.sb-entering', '.sb-pop-in', '.sb-drawer-in', '.sb-sheet-in', '.sb-draw-in', '.sb-draw-in-radial'];
const NEW_CLASSES = [...ENTRANCES, '.sb-drawer-out', '.sb-fade-out', `${STAGGER}*`];

describe('styles/motion.css: the one motion home (v168 §2)', () => {
  it('is imported by styles.css right after tokens.css', () => {
    const imports = [...STYLES.matchAll(/@import\s+'([^']+)';/g)].map(([, path]) => path);
    expect(imports).toContain('./styles/tokens.css');
    expect(imports.indexOf('./styles/motion.css')).toBe(imports.indexOf('./styles/tokens.css') + 1);
  });

  it('defines every keyframe exactly once, and no others', () => {
    const names = keyframeList(MOTION).map(([name]) => name);
    expect([...names].sort()).toEqual([...KEYFRAMES].sort());
  });

  it('took the flash out of styles.css', () => {
    expect(STYLES).not.toMatch(/@keyframes/);
    expect(STYLES).not.toMatch(/\.flash-(up|down)\s*\{/);
  });

  it('merges the four pulse copies by shape, each shape unchanged (amendment 7)', () => {
    const body = Object.fromEntries(keyframeList(MOTION));
    expect(body['sb-pulse-soft']).toBe('50% { opacity: 0.45; }');
    expect(body['sb-pulse-dim']).toBe('50% { opacity: 0.35; }');
    expect(body['sb-pulse-blink']).toBe('0%, 100% { opacity: 1; } 50% { opacity: 0.25; }');
    expect(body['sb-spin']).toBe('to { transform: rotate(360deg); }');
  });

  it('zeroes the scale only under Off', () => {
    const scaled = rules(MOTION).filter(({ body }) => body.includes('--motion-scale:'));
    expect(scaled).toEqual([{ selector: '[data-motion=off]', body: '--motion-scale: 0;' }]);
  });

  it('animates only compositor-friendly properties in the new keyframes', () => {
    const body = Object.fromEntries(keyframeList(MOTION));
    for (const name of NEW_KEYFRAMES) {
      const properties = [...body[name].matchAll(/([\w-]+)\s*:/g)].map(([, property]) => property);
      expect(properties.length, name).toBeGreaterThan(0);
      expect(properties.filter((property) => !COMPOSITOR.has(property)), name).toEqual([]);
    }
  });

  it('refines the cell flash: 1.1s, tint plus the tier-3 text colour (#8)', () => {
    const body = Object.fromEntries(keyframeList(MOTION));
    expect(bodiesFor(MOTION, '.flash-up')).toEqual(['animation: sb-flash-up calc(1100ms * var(--motion-scale)) var(--ease-out);']);
    expect(bodiesFor(MOTION, '.flash-down')).toEqual(['animation: sb-flash-down calc(1100ms * var(--motion-scale)) var(--ease-out);']);
    expect(body['sb-flash-up']).toBe('from { background: var(--pos-soft); color: var(--flash-up-text); } to { background: transparent; }');
    expect(body['sb-flash-down']).toBe('from { background: var(--neg-soft); color: var(--flash-down-text); } to { background: transparent; }');
  });
});

describe('the motion classes (v168 §3)', () => {
  it('holds every entrance at its first frame with fill-mode backwards', () => {
    for (const cls of [...ENTRANCES, `${STAGGER}*`]) {
      const animations = bodiesFor(MOTION, cls).filter((body) => body.includes('animation:'));
      expect(animations.length, cls).toBeGreaterThan(0);
      for (const body of animations) expect(body, cls).toMatch(/animation: [^;]*\bbackwards;/);
    }
  });

  it('holds every exit at its last frame', () => {
    expect(bodiesFor(MOTION, '.sb-drawer-out')[0]).toMatch(/animation: sb-drawer-out [^;]*\bforwards;/);
    expect(bodiesFor(MOTION, '.sb-fade-out')[0]).toMatch(/animation: sb-fade-out [^;]*\bforwards;/);
  });

  it('staggers 60ms apart from 640px, capped at the eighth child', () => {
    const delays = Object.fromEntries(
      rules(blocksOf(MOTION, '@media (min-width: 640px)'))
        .filter(({ selector }) => selector.startsWith(STAGGER))
        .map(({ selector, body }) => [selector.slice(STAGGER.length), body]),
    );
    const step = (ms: number) => `animation-delay: calc(${ms}ms * var(--motion-scale));`;
    expect(delays).toEqual({
      ':nth-child(2)': step(60),
      ':nth-child(3)': step(120),
      ':nth-child(4)': step(180),
      ':nth-child(5)': step(240),
      ':nth-child(6)': step(300),
      ':nth-child(7)': step(360),
      ':nth-child(n + 8)': step(420),
    });
  });

  it('staggers 40ms apart below 640px, capped at the fourth child', () => {
    const delays = Object.fromEntries(
      rules(blocksOf(MOTION, '@media (max-width: 639px)'))
        .filter(({ selector }) => selector.startsWith(STAGGER))
        .map(({ selector, body }) => [selector.slice(STAGGER.length), body]),
    );
    const step = (ms: number) => `animation-delay: calc(${ms}ms * var(--motion-scale));`;
    expect(delays).toEqual({ ':nth-child(2)': step(40), ':nth-child(3)': step(80), ':nth-child(n + 4)': step(120) });
  });

  it('lifts on hover only where hover exists, and moves only under On (#5)', () => {
    const hover = blocksOf(MOTION, '@media (hover: hover)');
    expect(bodiesFor(hover, '[data-motion] .sb-lift:hover')).toEqual([
      'border-color: var(--border-strong); box-shadow: var(--panel-shadow-lift);',
    ]);
    expect(bodiesFor(hover, '[data-motion=on] .sb-lift:hover')).toEqual(['transform: translateY(-2px);']);
    expect(MOTION.match(/translateY\(-2px\)/g)).toHaveLength(1);
    expect(bodiesFor(blocksOf(MOTION, '@media (hover: none)'), '[data-motion] .sb-lift:active')).toEqual([
      'box-shadow: inset 0 0 0 100vmax var(--accent-soft);',
    ]);
  });

  it('turns the drawer into a rising sheet below 640px (#7)', () => {
    const phone = blocksOf(MOTION, '@media (max-width: 639px)');
    expect(bodiesFor(phone, 'sb-drawer dialog.sb-drawer-in')).toEqual(['animation-name: sb-sheet-in;']);
    expect(bodiesFor(phone, 'sb-drawer dialog.sb-drawer-out')).toEqual(['animation-name: sb-sheet-out;']);
  });

  it('fades and blurs the dialog backdrops in (#7)', () => {
    for (const host of ['sb-drawer', 'sb-confirm-dialog']) {
      expect(bodiesFor(MOTION, `${host} dialog[open]::backdrop`)).toEqual([
        'backdrop-filter: blur(2px); animation: sb-fade-in calc(200ms * var(--motion-scale)) var(--ease-out) backwards;',
      ]);
    }
  });

  it('sets will-change only on classes that come off when their animation ends (§6)', () => {
    const TRANSIENT = new Set(['.sb-entering', '.sb-drawer-in', '.sb-sheet-in', '.sb-drawer-out', '.sb-draw-in', '.sb-draw-in-radial']);
    const holders = rules(MOTION)
      .filter(({ body }) => body.includes('will-change'))
      .flatMap(({ selector }) => splitList(selector));
    expect(holders.length).toBeGreaterThan(0);
    expect(holders.filter((selector) => !TRANSIENT.has(selector))).toEqual([]);
  });
});

describe('the mode rules for the new classes (v168 §1)', () => {
  it('stops every new animation under Off and while preferences load', () => {
    for (const mode of ['off', 'pending']) {
      for (const cls of NEW_CLASSES) {
        expect(bodiesFor(MOTION, `[data-motion=${mode}] ${cls}`), `${mode} ${cls}`).toContain('animation: none;');
      }
      for (const host of ['sb-drawer', 'sb-confirm-dialog']) {
        expect(bodiesFor(MOTION, `[data-motion=${mode}] ${host} dialog[open]::backdrop`)).toContain('animation: none;');
      }
    }
  });

  it('turns entrances and the dialogs into a plain fade under Reduced', () => {
    for (const cls of ['.sb-enter', '.sb-entering', `${STAGGER}*`, '.sb-pop-in', '.sb-drawer-in', '.sb-sheet-in']) {
      expect(bodiesFor(MOTION, `[data-motion=reduced] ${cls}`), cls).toContain(
        'animation-name: sb-fade-in; animation-duration: var(--dur-base);',
      );
    }
    expect(bodiesFor(MOTION, '[data-motion=reduced] .sb-drawer-out')).toContain('animation-name: sb-fade-out;');
  });

  it('draws no chart in under Reduced (#9)', () => {
    for (const cls of ['.sb-draw-in', '.sb-draw-in-radial']) {
      expect(bodiesFor(MOTION, `[data-motion=reduced] ${cls}`), cls).toContain('animation: none;');
    }
  });

  it('drifts the ambient glow under On only, and never on a phone (#10)', () => {
    expect(bodiesFor(MOTION, '[data-motion=on] .ambient')).toContain('animation: sb-ambient-drift 12s ease-in-out infinite alternate;');
    expect(bodiesFor(blocksOf(MOTION, '@media (max-width: 639px)'), '[data-motion=on] .ambient')).toEqual(['animation: none;']);
    const unscoped = rules(MOTION).filter(({ selector }) => selector.includes('.ambient') && !selector.includes('[data-motion=on]'));
    expect(unscoped).toEqual([]);
  });

  it('stills the live-dot ping outside On (#10)', () => {
    for (const mode of ['reduced', 'off', 'pending']) {
      expect(bodiesFor(MOTION, `[data-motion=${mode}] sb-connection-status .dot.live::after`), mode).toEqual([
        'animation: none; opacity: 0;',
      ]);
    }
  });

  it('gives the skeleton a static tint under Reduced and Off (#4)', () => {
    for (const mode of ['reduced', 'off']) {
      expect(bodiesFor(MOTION, `[data-motion=${mode}] sb-async .skeleton-cell`), mode).toContain('animation: none;');
    }
  });

  it('slides the nav indicator on a spring under On, fades it under Reduced (#6)', () => {
    expect(bodiesFor(MOTION, '[data-motion=on] sb-nav-indicator .nav-indicator')).toEqual([
      'transition: transform calc(350ms * var(--motion-scale)) var(--ease-spring), opacity var(--dur-base) var(--ease-out);',
    ]);
    expect(bodiesFor(MOTION, '[data-motion=reduced] sb-nav-indicator .nav-indicator')).toEqual([
      'transition: opacity var(--dur-base) var(--ease-out);',
    ]);
  });
});

describe('Off keeps every fallback (spec v168 §1)', () => {
  /* Whitespace-flattened, so a rule is asserted by its text whatever the line
   * breaks. Read from disk, never `?raw` (see tokens.spec.ts's header). */
  const fallbackCss = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8')
    .replace(/\s+/g, ' ');
  const readSource = (path: string) => readFileSync(join(process.cwd(), 'src', path), 'utf8');
  const frozen = ':is([data-motion=off], [data-motion=reduced], [data-motion=pending])';

  const fallbackSites: { site: string; file: string; rules: string[] }[] = [
    {
      site: 'tokens.css global block',
      file: 'styles/tokens.css',
      rules: ['[data-motion=off] { --motion-scale: 0; }'],
    },
    {
      site: 'connection-status live dot',
      file: 'app/shell/connection-status.ts',
      rules: ['[data-motion=off] sb-connection-status .dot.live { animation: none !important; }'],
    },
    {
      site: 'scan-progress strip and sweep',
      file: 'app/shell/scan-progress.css',
      rules: [
        '[data-motion=off] sb-scan-progress .strip { animation: none !important; }',
        '[data-motion=off] sb-scan-progress .fill { transition: none !important; }',
        '[data-motion=off] sb-scan-progress .fill.sweeping { animation: none !important; width: 100% !important; opacity: .4 !important; }',
      ],
    },
    {
      site: 'shell sidebar width and route spinner',
      file: 'app/shell/shell.css',
      rules: [
        '[data-motion=off] sb-shell .shell, [data-motion=off] sb-shell .shell.overlay .sidebar { transition: none !important; }',
        '[data-motion=off] sb-shell .route-loading-mark { animation-duration: 2.4s !important; }',
      ],
    },
    {
      site: 'tape track',
      file: 'app/shell/tape/tape.css',
      rules: [
        `${frozen} sb-tape .track { animation: none !important; }`,
        `${frozen} sb-tape .viewport { overflow-x: auto !important; }`,
      ],
    },
    {
      site: 'data-table spinner and blinking row',
      file: 'app/ui/data-table/data-table.ts',
      rules: [
        '[data-motion=off] sb-data-table .loading-spinner { animation-duration: 2.4s !important; }',
        '[data-motion=off] sb-data-table .blink { animation: none !important; background: color-mix(in srgb, var(--warn) 10%, transparent) !important; }',
      ],
    },
    {
      site: 'chart-container spinner',
      file: 'app/ui/chart-container.ts',
      rules: ['[data-motion=off] sb-chart-container .spinner { animation-duration: 2.4s !important; }'],
    },
    {
      site: 'status-indicator open dot',
      file: 'app/ui/status-indicator.ts',
      rules: ['[data-motion=off] sb-status-indicator .open { animation: none !important; }'],
    },
    {
      site: 'status-cell dot and fill',
      file: 'app/ui/status-cell.ts',
      rules: [
        '[data-motion=off] sb-status-cell .dot { animation: none !important; }',
        '[data-motion=off] sb-status-cell .fill { transition: none !important; }',
      ],
    },
  ];

  for (const { site, file, rules } of fallbackSites) {
    it(`${site}: carries its [data-motion] fallback and no OS media block`, () => {
      for (const rule of rules) expect(fallbackCss).toContain(rule);
      expect(readSource(file)).not.toContain('prefers-reduced-motion');
    });
  }

  it('never stops a spinner: loading spinners only slow down', () => {
    const stops = /(?:spinner|route-loading-mark)[^{}]*\{[^}]*animation:\s*none/;
    /* Comments stripped: prose naming a spinner must not pair with the next rule. */
    expect(fallbackCss.replace(/\/\*.*?\*\//g, '')).not.toMatch(stops);
  });
});
