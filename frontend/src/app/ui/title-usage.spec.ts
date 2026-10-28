import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

import { TITLE_ALLOW, TITLE_INPUT_ELEMENTS, TITLE_PENDING } from './title-usage.allow';

const ROOT = join(process.cwd(), 'src/app');

/** `title="…"`, `[title]="…"`, `[attr.title]="…"` after whitespace, or the
 *  host-metadata key `'[attr.title]': '…'`. */
const SITE = /(?<=\s)(?:\[attr\.title\]|\[title\]|title)="[^"]*"|'\[attr\.title\]':\s*'[^']*'/g;

interface Found { file: string; binding: string }

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return path === join(ROOT, 'testing') ? [] : sourceFiles(path);
    // The allow-list quotes the very bindings it lists, so it is not scanned.
    return name.endsWith('.ts') && !name.endsWith('.spec.ts') && name !== 'title-usage.allow.ts' ? [path] : [];
  });
}

/** The element an attribute at `index` sits on: the nearest `<` before it
 *  with no `>` in between. Null outside a tag (host metadata). */
function enclosingTag(source: string, index: number): string | null {
  const open = source.lastIndexOf('<', index);
  if (open < 0 || source.lastIndexOf('>', index) > open) return null;
  return /^<([a-z][\w-]*)/i.exec(source.slice(open))?.[1].toLowerCase() ?? null;
}

function findTitleSites(file: string, source: string): Found[] {
  const found: Found[] = [];
  for (const match of source.matchAll(SITE)) {
    const tag = enclosingTag(source, match.index!);
    if (tag !== null && TITLE_INPUT_ELEMENTS.includes(tag)) continue;
    found.push({ file, binding: match[0].replace(/\s+/g, ' ') });
  }
  return found;
}

function scan(): Found[] {
  return sourceFiles(ROOT).flatMap((path) =>
    findTitleSites(relative(ROOT, path).split('\\').join('/'), readFileSync(path, 'utf8')));
}

const key = (s: Found): string => `${s.file} :: ${s.binding}`;

describe('findTitleSites', () => {
  it('finds plain, bound and attr titles, and host metadata', () => {
    const src = `template: \`<span title="a">x</span> <b [title]="b()"></b> <i [attr.title]="c"></i>\`,
      host: { '[attr.title]': 'd()' },`;
    expect(findTitleSites('f.ts', src).map((s) => s.binding)).toEqual([
      'title="a"', '[title]="b()"', '[attr.title]="c"', "'[attr.title]': 'd()'",
    ]);
  });

  it('skips title inputs of heading components, one line or several', () => {
    const src = `<sb-panel-header title="Equity" [n]="3" />
      <sb-confirm-dialog
        [open]="x"
        title="Delete this?"
      />
      <sb-empty-state [title]="error()!" />`;
    expect(findTitleSites('f.ts', src)).toEqual([]);
  });

  it('ignores names that only end in "title"', () => {
    const src = `<x subtitle="a" data-title="b" [pageTitle]="c"></x>`;
    expect(findTitleSites('f.ts', src)).toEqual([]);
  });

  it('counts two identical bindings in one file twice', () => {
    expect(findTitleSites('f.ts', `<a [title]="r"></a> <b [title]="r"></b>`)).toHaveLength(2);
  });
});

describe('native title usage (v194 A3)', () => {
  const found = scan();

  it('lists every title binding in the allow-list, so no new explanation hides in a title', () => {
    const allowed = new Map<string, number>();
    for (const s of TITLE_ALLOW) allowed.set(key(s), (allowed.get(key(s)) ?? 0) + 1);
    const unlisted = found.filter((s) => {
      const left = allowed.get(key(s)) ?? 0;
      allowed.set(key(s), left - 1);
      return left <= 0;
    });
    expect(unlisted.map(key)).toEqual([]);
  });

  it('keeps no stale allow-list entry once a site is converted', () => {
    expect(found.map(key).sort()).toEqual(TITLE_ALLOW.map(key).sort());
  });

  it('gives every entry a reason', () => {
    expect(TITLE_ALLOW.filter((s) => s.note.trim() === '')).toEqual([]);
  });

  it('marks as pending exactly the explanation sites', () => {
    expect(TITLE_PENDING).toEqual(TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending'));
    expect(TITLE_PENDING.some((s) => s.file.startsWith('workspaces/analytics/'))).toBe(false);
  });
});
