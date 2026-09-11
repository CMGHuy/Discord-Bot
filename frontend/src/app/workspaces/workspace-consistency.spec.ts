import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = join(process.cwd(), 'src/app/workspaces');

/** Every workspace component file, excluding specs and the gallery. */
function workspaceSources(): { name: string; path: string; source: string }[] {
  const out: { name: string; path: string; source: string }[] = [];
  for (const dir of readdirSync(ROOT, { withFileTypes: true })) {
    if (!dir.isDirectory() || dir.name === 'gallery') continue;
    for (const file of readdirSync(join(ROOT, dir.name))) {
      if (!file.endsWith('.ts') || file.endsWith('.spec.ts') || file.endsWith('.routes.ts')) continue;
      const path = join(ROOT, dir.name, file);
      out.push({ name: `${dir.name}/${file}`, path, source: readFileSync(path, 'utf8') });
    }
  }
  return out;
}

const SOURCES = workspaceSources();

describe('workspace consistency (v85)', () => {
  it('finds workspace sources at all', () => {
    expect(SOURCES.length).toBeGreaterThan(0);
  });

  it('renders no in-page heading — the top bar owns the title (D4)', () => {
    const offenders = SOURCES.filter((s) => /<h1[\s>]/.test(s.source)).map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('uses sb-panel rather than a hand-rolled card', () => {
    const offenders = SOURCES
      .filter((s) => /class="panel"/.test(s.source) && !/sb-panel/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('uses the shared control bar wherever a page has filters (D22)', () => {
    const offenders = SOURCES
      .filter((s) => /sb-filter-bar|class="filters"/.test(s.source) && !/sb-control-bar/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('sizes metric grids with auto-fit rather than a fixed column count', () => {
    const offenders = SOURCES
      .filter((s) => /grid-template-columns:\s*repeat\(\s*\d/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });

  it('declares a freshness marker on every page that fetches (D30)', () => {
    const offenders = SOURCES
      .filter((s) => /sb-async/.test(s.source) && !/sb-freshness/.test(s.source))
      .map((s) => s.name);
    expect(offenders).toEqual([]);
  });
});
