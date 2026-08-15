import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

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

const REQUIRED = [
  '--bg',
  '--surface',
  '--surface-raised',
  '--surface-overlay',
  '--border',
  '--border-strong',

  '--text',
  '--text-secondary',
  '--text-muted',
  '--text-faint',

  '--pos',
  '--neg',
  '--warn',
  '--accent',
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

  '--dur-instant',
  '--dur-base',
  '--dur-slow',
  '--ease-out',
  '--ease-spring',

  '--control-h',
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

  it('honours prefers-reduced-motion', () => {
    expect(CSS).toContain('prefers-reduced-motion: reduce');
  });

  it('has dropped --space-28', () => {
    expect(CSS).not.toMatch(/^\s*--space-28:/m);
  });

  it('has dropped the old greyscale quality tokens', () => {
    for (const dead of ['--quality-high', '--quality-mid', '--quality-low']) {
      expect(CSS).not.toMatch(new RegExp(`^\\s*${dead}:`, 'm'));
    }
  });

  it('keeps --transition as an alias so existing call sites still compile', () => {
    expect(CSS).toMatch(/^\s*--transition:/m);
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
  for (const dir of readdirSync(WORKSPACES)) {
    for (const file of readdirSync(join(WORKSPACES, dir))) {
      if (!file.endsWith('.ts') || file.endsWith('.spec.ts')) continue;
      out.push({
        name: `${dir}/${file}`,
        source: readFileSync(join(WORKSPACES, dir, file), 'utf8'),
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
  'realized', // two metric cards beside a closed-trade tally
  'chip', // the inside of a bordered chip, not a row of controls
  'scan', // the scan-duration figures beside their sparkline
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
