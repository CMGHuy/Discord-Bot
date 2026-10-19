import { readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Spec v168 §2: every @keyframes in the app lives in styles/motion.css, and
 * every animation names one of them.
 *
 * Before v168, `pulse` was declared four times in three different shapes
 * and `spin` twice; a fifth copy would have been one more silent variant.
 * Keyframe names are global, so a component references motion.css's names
 * directly.
 *
 * The walk covers every .ts and .css under src/ (styles/ included, which
 * v167's allSources() skips), names relative to src/ with `/`. Spec files
 * are excluded, this one included: they quote CSS on purpose. Sources are
 * read with readFileSync from process.cwd(), never `?raw` (tokens.spec.ts
 * records why).
 */
const SRC = join(process.cwd(), 'src');
const KEYFRAME_HOME = 'styles/motion.css';

function sourceFiles(): { name: string; source: string }[] {
  const found: { name: string; source: string }[] = [];
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(path);
        continue;
      }
      if (!/\.(ts|css)$/.test(entry.name) || entry.name.endsWith('.spec.ts')) continue;
      found.push({ name: relative(SRC, path).split(sep).join('/'), source: readFileSync(path, 'utf8') });
    }
  };
  walk(SRC);
  return found.sort((a, b) => a.name.localeCompare(b.name));
}

const uncomment = (source: string) => source.replace(/\/\*[\s\S]*?\*\//g, '');
const KEYFRAME_DECL = /@keyframes\s+([\w-]+)\s*\{/g;
/** `animation: <name> …` and `animation-name: <name>`; keywords are not names. */
const ANIMATION_REF = /\banimation(?:-name)?:\s*([a-z][\w-]*)/g;
const NOT_A_NAME = new Set(['none', 'inherit', 'initial', 'unset', 'revert', 'var', 'calc']);

describe('one keyframe home (v168 §2)', () => {
  const files = sourceFiles();

  it('walks the sources it is meant to', () => {
    const names = files.map(({ name }) => name);
    expect(names).toContain(KEYFRAME_HOME);
    expect(names).toContain('styles.css');
    expect(names).toContain('app/ui/async.ts');
    expect(names).toContain('app/shell/scan-progress.css');
    expect(names.filter((name) => name.endsWith('.spec.ts'))).toEqual([]);
  });

  it('declares @keyframes only in styles/motion.css', () => {
    const offenders = files
      .filter(({ name, source }) => name !== KEYFRAME_HOME && /@keyframes\s+[\w-]+\s*\{/.test(uncomment(source)))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });

  it('names only keyframes that motion.css defines', () => {
    const home = files.find(({ name }) => name === KEYFRAME_HOME)!;
    const defined = new Set([...uncomment(home.source).matchAll(KEYFRAME_DECL)].map(([, name]) => name));
    const unknown = files.flatMap(({ name, source }) =>
      [...uncomment(source).matchAll(ANIMATION_REF)]
        .map(([, ref]) => ref)
        .filter((ref) => !NOT_A_NAME.has(ref) && !defined.has(ref))
        .map((ref) => `${name}: ${ref}`),
    );
    expect(unknown).toEqual([]);
  });
});

describe('the OS reduced-motion setting (spec v168 D2)', () => {
  /* Matches the media feature as a query uses it -- "(prefers-reduced-motion"
   * in an @media rule or a matchMedia() string -- so prose that names the
   * feature is not an offence. flash.ts's doc comment still names it until
   * MO14 rewrites that comment; that is prose, not a query. */
  it('no prefers-reduced-motion outside specs', () => {
    const offenders = sourceFiles()
      .filter(({ source }) => /\(\s*prefers-reduced-motion\b/.test(source))
      .map(({ name }) => name);
    expect(offenders).toEqual([]);
  });
});
