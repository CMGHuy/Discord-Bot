import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { GATED_CALLERS, WRITE_CALLS, WriteGate } from './write-calls';

const ROOT = join(process.cwd(), 'src/app');
const read = (path: string) => readFileSync(join(ROOT, path), 'utf8');

const walk = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
  const path = join(dir, name);
  return statSync(path).isDirectory() ? walk(path) : [path];
});
const SOURCES = walk(ROOT)
  .filter((path) => path.endsWith('.ts') && !path.endsWith('.spec.ts'))
  .map((path) => relative(ROOT, path).replaceAll('\\', '/'));

/** ApiClient methods whose body makes a non-GET call: the method name is the
 *  last two-space-indented `name(` line above the `this.http.<verb>` call. */
function mutatingMethods(): string[] {
  const found = new Set<string>();
  let current: string | null = null;
  for (const line of read('api/api-client.ts').split('\n')) {
    const signature = /^ {2}([A-Za-z]\w*)\s*\(/.exec(line);
    if (signature) current = signature[1];
    if (current && /this\.http\.(post|put|patch|delete|request)\b/.test(line)) found.add(current);
  }
  return [...found].sort();
}

describe('WRITE_CALLS (v207)', () => {
  it('lists every mutating ApiClient method, and nothing else', () => {
    expect(mutatingMethods().length).toBeGreaterThanOrEqual(26);
    expect(Object.keys(WRITE_CALLS).sort()).toEqual(mutatingMethods());
  });

  it('has no HttpClient write outside ApiClient, so the list above is the whole surface', () => {
    const writers = SOURCES
      .filter((path) => path !== 'api/api-client.ts')
      .filter((path) => /\b(?:http|httpClient|client)\.(post|put|patch|delete|request)\s*[<(]/.test(read(path)));
    expect(writers).toEqual([]);
  });

  it('keeps sign-in and sign-out public, and only those', () => {
    const publicCalls = Object.entries(WRITE_CALLS).filter(([, gate]) => gate === 'public').map(([name]) => name).sort();
    expect(publicCalls).toEqual(['login', 'logout']);
  });

  it.each(['admin-route', 'hidden-tab', 'store-no-save'] as WriteGate[])(
    'calls every %s method only from the places that gate allows',
    (gate) => {
      const allowed = GATED_CALLERS[gate]!;
      const inside = (path: string) => allowed.some((place) => (place.endsWith('/') ? path.startsWith(place) : path === place));
      const methods = Object.entries(WRITE_CALLS).filter(([, g]) => g === gate).map(([name]) => name);
      expect(methods.length).toBeGreaterThan(0);
      const strays = methods.flatMap((method) => SOURCES
        .filter((path) => path !== 'api/api-client.ts' && read(path).includes(`.${method}(`) && !inside(path))
        .map((path) => `${method} <- ${path}`));
      expect(strays).toEqual([]);
    },
  );
});
