import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

/** Static guards for the spacing rule. jsdom neither resolves var() nor lays
 * out the page, so these intentionally inspect the source text. */
const SRC = join(process.cwd(), 'src');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(ts|css)$/.test(name) && !name.endsWith('.spec.ts') ? [path] : [];
  });
}

const FILES = walk(SRC).map((path) => ({ path: relative(SRC, path).replace(/\\/g, '/'), text: readFileSync(path, 'utf8') }));

const RUNTIME_DEFINED = new Set<string>([
  '--heat', // calendar.ts binds [style.--heat] per cell
]);

function definedTokens(): Set<string> {
  const out = new Set<string>(RUNTIME_DEFINED);
  for (const { text } of FILES) {
    for (const m of text.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) out.add(m[1]);
    for (const m of text.matchAll(/\[style\.(--[a-zA-Z0-9-]+)\]/g)) out.add(m[1]);
    for (const m of text.matchAll(/setProperty\(\s*['\"](--[a-zA-Z0-9-]+)['\"]/g)) out.add(m[1]);
  }
  return out;
}

describe('design tokens are defined before they are used', () => {
  it('references no custom property that nothing defines', () => {
    const defined = definedTokens();
    const missing: string[] = [];
    for (const { path, text } of FILES) {
      const source = text.replace(/\/\*[\s\S]*?\*\//g, '');
      for (const m of source.matchAll(/var\((--[a-zA-Z0-9-]+)(\s*,)?/g)) {
        if (!m[2] && !defined.has(m[1])) missing.push(`${path}: ${m[1]}`);
      }
    }
    expect([...new Set(missing)]).toEqual([]);
  });
});

const PANEL_ELEMENTS = /^(sb-panel|sb-section-head|sb-async|sb-data-table|sb-exit-quality|sb-strategy-contribution)$/;
const LAYOUT_CLASSES = new Set(['panels', 'chart-grid', 'kpi-row', 'bottom-row', 'split', 'section', 'breakdowns', 'sb-stack', 'sb-row']);

/** Exceptions are removed by their owning UA8–UA13 task. */
export const PENDING_MARGIN_RULES: ReadonlySet<string> = new Set<string>([
  'app/workspaces/analytics/analytics.ts|sb-section-head',
  'app/workspaces/analytics/analytics.ts|sb-panel',
  'app/workspaces/analytics/analytics.ts|.section',
  'app/workspaces/analytics/analytics.ts|.kpi-row',
  'app/workspaces/analytics/analytics.ts|.breakdowns',
  'app/workspaces/analytics/analytics.ts|.breakdowns > * + *',
]);

function stylesOf(text: string): string {
  const at = text.indexOf('styles:');
  return (at < 0 ? '' : text.slice(at)).replace(/^styles:\s*`/, '').replace(/\/\*[\s\S]*?\*\//g, '');
}

function panelClassesOf(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.matchAll(/<sb-panel\b[^>]*?\bclass="([^"]+)"/g)) {
    m[1].split(/\s+/).forEach((c) => out.add(c));
  }
  return out;
}

function isPanelLevel(selector: string, panelClasses: Set<string>): boolean {
  const last = selector.trim().split(/\s+/).pop() ?? '';
  if (PANEL_ELEMENTS.test(last)) return true;
  const cls = /^\.([a-zA-Z0-9_-]+)/.exec(selector.trim());
  return cls !== null && (LAYOUT_CLASSES.has(cls[1]) || panelClasses.has(cls[1]));
}

describe('spacing between panels comes from the stack gap, not margins', () => {
  it('declares no outer margin on a panel-level selector', () => {
    const offenders: string[] = [];
    for (const { path, text } of FILES.filter((f) => f.path.startsWith('app/workspaces/'))) {
      const panelClasses = panelClassesOf(text);
      for (const m of stylesOf(text).matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const body = m[2];
        const margin = /margin(-top|-bottom|-block)?\s*:\s*([^;]+)/.exec(body);
        if (!margin || /^\s*(0|auto)\s*$/.test(margin[2])) continue;
        for (const selector of m[1].split(',').map((s) => s.trim()).filter(Boolean)) {
          if (!isPanelLevel(selector, panelClasses)) continue;
          const key = `${path}|${selector}`;
          if (!PENDING_MARGIN_RULES.has(key)) offenders.push(key);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
