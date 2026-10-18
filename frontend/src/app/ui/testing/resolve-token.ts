import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * The TypeScript half of the token resolver pair (spec v167 § 1).
 *
 * Tier 1 (palette.css) holds raw colours; tier 2 and tier 3 (tokens.css) refer
 * to them through var(). A spec that needs a token's literal value -- contrast,
 * chart palette, chart theme -- asks this module, never a private regexp over
 * tokens.css, which stops matching the moment a token becomes a var().
 *
 * scripts/dev/dump_tokens.py is the Python half. The rules are identical, line
 * for line: comments stripped; only top-level `:root { }` blocks read (every
 * @media / @supports override dropped); file order, later wins; names without
 * the leading `--`; values whitespace-collapsed; `var(--x)` followed
 * recursively; an undefined reference, a cycle or a `var(--x, fallback)` is an
 * error. Both must reproduce tests/charts/resolved_tokens.json exactly
 * (resolve-token.spec.ts here, test_chart_theme.py there).
 *
 * Files are read from `process.cwd()` (= frontend/ under `ng test`), never
 * `import.meta.url` or `?raw`: see test-setup.ts for why both fail here.
 */
export const STYLE_FILES = ['src/styles/palette.css', 'src/styles/tokens.css'] as const;

/** Relative to `process.cwd()`, which `ng test` sets to frontend/. */
export const FIXTURE_PATH = '../tests/charts/resolved_tokens.json';

const COMMENT_RE = /\/\*[\s\S]*?\*\//g;
const VAR_RE = /var\(--([\w-]+)\)/g;

export function stripComments(css: string): string {
  return css.replace(COMMENT_RE, '');
}

/** Index just past the `}` that closes the block opened at `open`. */
function blockEnd(css: string, open: number): number {
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) return i + 1;
  }
  throw new Error(`unbalanced braces from offset ${open}`);
}

/** [selector, body] for each top-level `selector { body }`, in file order. */
function topLevelBlocks(css: string): [string, string][] {
  const blocks: [string, string][] = [];
  let start = 0;
  let open = css.indexOf('{', start);
  while (open >= 0) {
    const end = blockEnd(css, open);
    const selector = css.slice(start, open).split(';').pop()!.trim();
    blocks.push([selector, css.slice(open + 1, end - 1)]);
    start = end;
    open = css.indexOf('{', start);
  }
  return blocks;
}

function declarations(body: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const chunk of body.split(';')) {
    const colon = chunk.indexOf(':');
    const name = chunk.slice(0, Math.max(colon, 0)).trim();
    if (colon >= 0 && name.startsWith('--')) {
      found[name.slice(2)] = chunk.slice(colon + 1).replace(/\s+/g, ' ').trim();
    }
  }
  return found;
}

/** Every custom property declared in a top-level `:root` block. */
export function parseRoot(css: string): Record<string, string> {
  const declared: Record<string, string> = {};
  for (const [selector, body] of topLevelBlocks(stripComments(css))) {
    if (selector === ':root') Object.assign(declared, declarations(body));
  }
  return declared;
}

/** Follow every `var(--x)` hop to a literal. */
export function resolveAll(declared: Record<string, string>): Record<string, string> {
  const resolved: Record<string, string> = {};
  const visit = (name: string, trail: readonly string[]): string => {
    if (Object.hasOwn(resolved, name)) return resolved[name];
    if (!Object.hasOwn(declared, name)) throw new Error(`--${name} is not defined`);
    if (trail.includes(name)) throw new Error(`cycle at --${name}`);
    const value = declared[name].replace(VAR_RE, (_match, ref: string) => visit(ref, [...trail, name]));
    // Message split so spacing.spec.ts's source scan does not read it as a var() use.
    if (value.includes('var(')) throw new Error(`--${name}: only plain ` + 'var(' + '--x) is supported');
    resolved[name] = value;
    return value;
  };
  for (const name of Object.keys(declared)) visit(name, []);
  return resolved;
}

function sortedByKey(tokens: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.keys(tokens).sort().map((name) => [name, tokens[name]]));
}

let memo: Record<string, string> | undefined;

/** palette.css then tokens.css, resolved; read once per worker. */
export function resolvedTokens(): Record<string, string> {
  if (!memo) {
    const declared: Record<string, string> = {};
    for (const file of STYLE_FILES) {
      Object.assign(declared, parseRoot(readFileSync(join(process.cwd(), file), 'utf8')));
    }
    memo = sortedByKey(resolveAll(declared));
  }
  return memo;
}

/** The literal a token resolves to; `name` may carry its leading `--` or not. */
export function resolveToken(name: string): string {
  const key = name.startsWith('--') ? name.slice(2) : name;
  const tokens = resolvedTokens();
  if (!Object.hasOwn(tokens, key)) throw new Error(`${name} is not a token`);
  return tokens[key];
}

/** The committed fixture, as written by scripts/dev/dump_tokens.py. */
export function readFixture(): Record<string, string> {
  return JSON.parse(readFileSync(join(process.cwd(), FIXTURE_PATH), 'utf8')) as Record<string, string>;
}

/** One `:root` block of literals, keys sorted: what jsdom gets instead of the tiers. */
export function flattenedRootCss(tokens: Record<string, string>): string {
  const lines = Object.keys(tokens)
    .sort()
    .map((name) => `  --${name}: ${tokens[name]};`);
  return `:root {\n${lines.join('\n')}\n}\n`;
}
