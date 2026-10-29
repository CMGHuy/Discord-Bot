import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';
import { resolveToken } from './testing/resolve-token';

const GLOBAL = readFileSync(join(process.cwd(), 'src/styles.css'), 'utf8');
const ui = (file: string) => readFileSync(join(process.cwd(), 'src/app/ui', file), 'utf8');

/**
 * The elevation ladder -- spec v167 §3, which supersedes v54 D2's one-shadow
 * law. In-flow panels cast --panel-shadow through the global .sb-panel
 * class; out-of-flow elements cast --shadow-overlay through .elev-overlay.
 * primitives.spec.ts G3 is the gate that nothing else casts a shadow.
 */
describe('the elevation ladder', () => {
  it('defines one in-flow panel rule carrying the panel shadow', () => {
    expect(GLOBAL).toMatch(/\.sb-panel\s*\{[^}]*box-shadow:\s*var\(--panel-shadow\)/s);
  });

  it('defines one overlay rule carrying the overlay shadow', () => {
    expect(GLOBAL).toMatch(/\.elev-overlay\s*\{[^}]*box-shadow:\s*var\(--shadow-overlay\)/s);
  });

  it('declares .sb-panel before .elev-overlay, so an overlay wins a tie', () => {
    const panel = GLOBAL.search(/\.sb-panel\s*\{/);
    expect(panel).toBeGreaterThan(-1);
    expect(panel).toBeLessThan(GLOBAL.search(/\.elev-overlay\s*\{/));
  });

  it('gives the overlay the raised surface, the strong border and the panel radius', () => {
    const rule = GLOBAL.match(/\.elev-overlay\s*\{[^}]*\}/s)![0];
    expect(rule).toContain('var(--surface-overlay)');
    expect(rule).toContain('var(--border-strong)');
    expect(rule).toContain('border-radius: var(--panel-radius)');
  });

  it('defines a scrim that uses the token rather than a raw rgba', () => {
    const rule = GLOBAL.match(/\.elev-scrim\s*\{[^}]*\}/s)![0];
    expect(rule).toContain('var(--scrim)');
    expect(rule).not.toMatch(/rgba?\(/);
  });

  /* v195 §1.2 retires v168 §3 #10: no ambient glow, on body or on a shell
   * layer. The page ground is the flat --bg. */
  it('paints no ambient glow anywhere', () => {
    expect(GLOBAL).toMatch(/body\s*\{[^}]*background:\s*var\(--bg\);/s);
    expect(stripComments(GLOBAL)).not.toContain('--glow-ambient');
    const painters = allSources()
      .filter(({ source }) => stripComments(source).includes('var(--glow-ambient)'))
      .map(({ name }) => name);
    expect(painters).toEqual([]);
    const shellHtml = readFileSync(join(process.cwd(), 'src/app/shell/shell.html'), 'utf8');
    expect(shellHtml).not.toMatch(/class="ambient"/);
  });
});

/**
 * The three panel-painting primitives read the tier-3 panel tokens and take
 * their shadow from .sb-panel, never from a box-shadow of their own.
 */
describe('the panel primitives paint the panel tokens (v167 §3)', () => {
  const PANEL = [
    'background: var(--panel-bg);',
    'border: var(--panel-border);',
    'border-radius: var(--panel-radius);',
  ];
  const expectPanelRule = (rule: string) => {
    for (const declaration of PANEL) expect(rule).toContain(declaration);
    expect(rule).not.toContain('var(--surface)');
    expect(rule).not.toContain('box-shadow');
  };

  it('sb-panel puts .sb-panel on its section and paints .panel from the tokens', () => {
    const source = ui('layout.ts');
    expect(source).toContain('<section class="panel sb-panel">');
    expectPanelRule(source.match(/\.panel\s*\{[^}]*\}/)![0]);
  });

  it('sb-figure-strip carries .sb-panel on its host and paints :host from the tokens', () => {
    const line = ui('figure.ts').split('\n').find((l) => l.includes("selector: 'sb-figure-strip'"))!;
    expect(line).toMatch(/host:\s*\{\s*class:\s*'sb-panel'/);
    expectPanelRule(line.match(/:host\s*\{[^}]*\}/)![0]);
  });

  it('sb-chart-container puts .sb-panel on its frame and paints .frame from the tokens', () => {
    const source = ui('chart-container.ts');
    expect(source).toContain('<figure class="frame sb-panel" [style.height.px]="height()">');
    expectPanelRule(source.match(/\.frame\s*\{[^}]*\}/)![0]);
  });
});

/**
 * v195 §1.2: depth comes only from the surface steps and 1px borders. The
 * panel is the --surface step with no gradient and no shadow; the overlay
 * shadow is the one shadow token left. .sb-panel still casts
 * var(--panel-shadow) (the rule above), and the token being `none` is what
 * makes it flat, so a later spec can restore depth in one place.
 */
describe('v195 §1.2: panels are flat', () => {
  const TOKENS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

  it('paints the panel on the surface step, not a gradient', () => {
    expect(TOKENS).toMatch(/^\s*--panel-bg:\s*var\(--surface\);/m);
    expect(resolveToken('--panel-bg')).toBe(resolveToken('--surface'));
  });

  it('casts no panel shadow', () => {
    expect(TOKENS).toMatch(/^\s*--panel-shadow:\s*none;/m);
  });

  it('keeps one shadow, on the overlay', () => {
    expect(resolveToken('--shadow-overlay')).not.toBe('none');
    expect(resolveToken('--shadow-overlay')).toMatch(/rgba\(0, 0, 0,/);
  });

  it('paints the primary button flat, with no gradient in either state', () => {
    expect(resolveToken('--btn-fill')).not.toMatch(/gradient/);
    expect(resolveToken('--btn-fill-hover')).not.toMatch(/gradient/);
  });
});

/* v195 Phase 2: dialogs, the drawer and toasts sit on the one overlay
 * surface (.elev-overlay: --surface-overlay, the strong hairline, the
 * panel radius) and cast the one --shadow-overlay through it; none paints
 * a surface or shadow of its own, and a modal dims with the --scrim token. */
describe('v195 Phase 2: one overlay surface', () => {
  const src = (path: string) => stripComments(readFileSync(join(process.cwd(), path), 'utf8'));
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const ruleOf = (source: string, selector: string) =>
    source.match(new RegExp(`\\n\\s*${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';
  const DIALOG = src('src/app/ui/confirm-dialog.ts');
  const LAYOUT = src('src/app/ui/layout.ts');
  const DRAWER = LAYOUT.slice(LAYOUT.indexOf("selector: 'sb-drawer'"), LAYOUT.indexOf('export class Drawer'));
  const TOAST = src('src/app/shell/toast-host.ts');

  it('puts the confirm dialog, the drawer and every toast on .elev-overlay', () => {
    expect(DIALOG).toContain('<dialog #dialog class="elev-overlay"');
    expect(DRAWER).toContain('<dialog #dialog class="drawer elev-overlay"');
    expect(TOAST).toContain('<button class="toast elev-overlay"');
  });

  it('paints no surface and casts no shadow of their own', () => {
    const own: [string, string][] = [
      ['dialog', ruleOf(DIALOG, 'dialog')],
      ['.drawer', ruleOf(DRAWER, '.drawer')],
      ['.drawer.elev-overlay', ruleOf(DRAWER, '.drawer.elev-overlay')],
      ['.toast', ruleOf(TOAST, '.toast')],
    ];
    for (const [name, rule] of own) {
      expect(rule, name).not.toBe('');
      expect(rule, name).not.toMatch(/background|box-shadow/);
    }
    for (const source of [DIALOG, DRAWER, TOAST]) expect(source).not.toMatch(/box-shadow\s*:/);
  });

  it('dims behind a modal with the scrim token', () => {
    expect(ruleOf(DIALOG, 'dialog::backdrop')).toContain('background: var(--scrim)');
    expect(ruleOf(DRAWER, '.drawer::backdrop')).toContain('background: var(--scrim)');
  });

  it('titles a dialog and a drawer alike, sentence case in the UI face', () => {
    for (const [name, source] of [['confirm-dialog', DIALOG], ['drawer', DRAWER]] as const) {
      const h2 = ruleOf(source, 'h2');
      for (const declaration of [
        'font-family: var(--font-sans);',
        'font-size: var(--text-subhead);',
        'font-weight: 600;',
        'letter-spacing: normal;',
      ]) expect(h2, `${name} ${declaration}`).toContain(declaration);
      expect(h2, name).not.toContain('text-transform');
    }
  });

  it('pads the drawer like a panel, following row density', () => {
    expect(ruleOf(DRAWER, 'header')).toContain('padding: var(--space-10) var(--panel-pad);');
    expect(ruleOf(DRAWER, '.body')).toContain('padding: var(--panel-pad);');
  });
});
