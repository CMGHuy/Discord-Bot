import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Every .ts, .css and .html under frontend/src: the scope of the colour and
 * radius gates (spec v167 §5, amendment 3). Unlike callSites() it reaches
 * ui/, testing/, every component stylesheet, styles.css and index.html.
 * Left out: *.spec.ts, and the styles/ directory (palette.css and
 * tokens.css, which primitives.spec.ts checks under their own rules).
 *
 * Names are relative to src/ with forward slashes ('app/ui/button.ts',
 * 'index.html') and sorted, so an allow-list Map keys on them on Windows
 * too. cwd is frontend/ under `ng test`, as for every spec in this repo.
 */
const SRC = join(process.cwd(), 'src');
const STYLES = join(SRC, 'styles');

export type Source = { name: string; source: string };

function scanned(entry: string): boolean {
  return /\.(ts|css|html)$/.test(entry) && !entry.endsWith('.spec.ts');
}

function walk(dir: string, out: Source[]): void {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (full !== STYLES) walk(full, out);
      continue;
    }
    if (!scanned(entry)) continue;
    const name = full.slice(SRC.length + 1).replace(/\\/g, '/');
    out.push({ name, source: readFileSync(full, 'utf8') });
  }
}

export function allSources(): Source[] {
  const out: Source[] = [];
  walk(SRC, out);
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Removes block comments, HTML comments and line comments, so a hex quoted
 * in prose (button.ts's contrast note) or a radius named in a comment stays
 * legal. A `//` counts as a comment only at the start of a line or after
 * whitespace: the `//` of `https://` follows a colon and is kept.
 */
export function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/(^|\s)\/\/[^\n]*/gm, '$1');
}
