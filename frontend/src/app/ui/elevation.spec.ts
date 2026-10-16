import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

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

  it('grounds the page on the ambient glow over --bg', () => {
    expect(GLOBAL).toMatch(/body\s*\{[^}]*background:\s*var\(--glow-ambient\),\s*var\(--bg\);/s);
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
    expect(source).toContain('<figure class="frame sb-panel"');
    expectPanelRule(source.match(/\.frame\s*\{[^}]*\}/)![0]);
  });
});
