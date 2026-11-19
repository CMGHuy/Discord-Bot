import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { parseGuideTarget } from '../../ui/guide-link';

/**
 * Spec v215 freshness layer 2: every `sb-guide-link` target in the app names
 * a chapter and heading that exist. The anchors come from
 * guide-anchors.json, which `python scripts/dev/guide_anchors.py` generates
 * from docs/guide/ and the backend test (`tests/scripts/test_guide_anchors.py`)
 * checks against the chapters, so the two sides cannot drift apart.
 */

interface AnchorFixture { chapters: Record<string, string[]> }
interface Placement { file: string; target: string }

const APP = join(process.cwd(), 'src/app');
const FIXTURE: AnchorFixture = JSON.parse(
  readFileSync(join(APP, 'workspaces/guide/guide-anchors.json'), 'utf8'));

const LITERAL = /<sb-guide-link\b[^>]*?\starget="([^"]*)"/g;
const BOUND = /<sb-guide-link\b[^>]*?\[target\]=/g;

function sources(dir: string = APP): { file: string; source: string }[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return sources(full);
    if (!/\.(ts|html)$/.test(entry.name) || entry.name.endsWith('.spec.ts')) return [];
    return [{ file: relative(APP, full).replace(/\\/g, '/'), source: readFileSync(full, 'utf8') }];
  });
}

function placements(files: { file: string; source: string }[]): Placement[] {
  return files.flatMap(({ file, source }) =>
    [...source.matchAll(LITERAL)].map((m) => ({ file, target: m[1] })));
}

function targetProblems(found: Placement[], fixture: AnchorFixture): string[] {
  return found.flatMap(({ file, target }) => {
    let slug: string;
    let anchor: string | null;
    try {
      ({ slug, anchor } = parseGuideTarget(target));
    } catch {
      return [`${file}: "${target}" names no chapter`];
    }
    const anchors = fixture.chapters[slug];
    if (!anchors) return [`${file}: "${target}" names no chapter "${slug}"`];
    if (anchor !== null && !anchors.includes(anchor)) {
      return [`${file}: "${target}" names no heading "${anchor}" in "${slug}"`];
    }
    return [];
  });
}

describe('guide-anchors.json', () => {
  it('is the generated shape: chapters keyed by slug, anchors as strings', () => {
    expect(Object.keys(FIXTURE)).toEqual(['chapters']);
    for (const [slug, anchors] of Object.entries(FIXTURE.chapters)) {
      expect(slug).toMatch(/^[a-z0-9-]+$/);
      expect(anchors.every((a) => typeof a === 'string' && a !== '')).toBe(true);
      expect(new Set(anchors).size).toBe(anchors.length);
    }
  });
});

describe('the anchor check itself', () => {
  const fixture: AnchorFixture = { chapters: { glossary: ['r-multiple'], pipeline: [] } };
  const at = (target: string) => [{ file: 'x.ts', target }];

  it('accepts a known chapter, alone or with a known heading', () => {
    expect(targetProblems(at('glossary'), fixture)).toEqual([]);
    expect(targetProblems(at('glossary#r-multiple'), fixture)).toEqual([]);
    expect(targetProblems(at('pipeline'), fixture)).toEqual([]);
  });

  it('names an unknown chapter, an unknown heading and an empty slug', () => {
    expect(targetProblems(at('nope'), fixture)).toEqual(['x.ts: "nope" names no chapter "nope"']);
    expect(targetProblems(at('glossary#nope'), fixture))
      .toEqual(['x.ts: "glossary#nope" names no heading "nope" in "glossary"']);
    expect(targetProblems(at('#r-multiple'), fixture)).toEqual(['x.ts: "#r-multiple" names no chapter']);
  });

  it('finds literal targets, with other attributes before them', () => {
    const files = [{ file: 'a.ts', source: '<sb-guide-link label="x" target="glossary#r-multiple" />' }];
    expect(placements(files)).toEqual([{ file: 'a.ts', target: 'glossary#r-multiple' }]);
  });
});

describe('every sb-guide-link in the app (v215 freshness layer 2)', () => {
  const files = sources();

  it('reads the app sources', () => {
    expect(files.some(({ file }) => file === 'ui/guide-link.ts')).toBe(true);
  });

  it('uses a literal target, so this spec can check it', () => {
    const bound = files
      .filter(({ source }) => { BOUND.lastIndex = 0; return BOUND.test(source); })
      .map(({ file }) => file);
    expect(bound).toEqual([]);
  });

  it('names an existing chapter and heading', () => {
    expect(targetProblems(placements(files), FIXTURE)).toEqual([]);
  });
});
