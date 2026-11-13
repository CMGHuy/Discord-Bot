import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  STYLE_FILES, declarations, parseRoot, resolveAll, resolveToken, stripComments, topLevelBlocks,
} from './resolve-token';

/**
 * Token values under each admin theme (spec v225). Test-only.
 *
 * resolve-token.ts and scripts/dev/dump_tokens.py read bare `:root` blocks
 * only, so they always answer Graphite -- which is what the jsdom fixture
 * and the Discord chart parity need. This helper layers the one
 * `:root[data-theme="navy"]` block of tokens.css over those `:root` blocks
 * and resolves again, for the specs that must measure Navy (contrast,
 * tokens, the cold-load copy). Never fold this into resolve-token.ts: its
 * Python twin would have to learn the theme too, and the Discord PNGs would
 * then be one resolver change away from Navy.
 */
export type TokenTheme = 'graphite' | 'navy';

export const TOKEN_THEMES: readonly TokenTheme[] = ['graphite', 'navy'];

export const NAVY_SELECTOR = ':root[data-theme="navy"]';

/** The ground and ink: the only tokens the Navy block re-points (tokens.css header). */
export const GROUND_INK_TOKENS: readonly string[] = [
  '--bg', '--surface', '--surface-raised', '--surface-overlay', '--overlay-dim',
  '--border', '--border-strong', '--text', '--text-secondary', '--text-muted', '--text-faint',
];

const read = (file: string) => readFileSync(join(process.cwd(), file), 'utf8');

/** The Navy block's declarations, `--` prefixed; exactly one block must exist. */
export function navyRepoints(css: string = read(STYLE_FILES[1])): Record<string, string> {
  const blocks = topLevelBlocks(stripComments(css)).filter(([selector]) => selector === NAVY_SELECTOR);
  if (blocks.length !== 1) throw new Error(`expected one ${NAVY_SELECTOR} block, found ${blocks.length}`);
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(declarations(blocks[0][1]))) out[`--${name}`] = value;
  return out;
}

let navyMemo: Record<string, string> | undefined;
function navyTokens(): Record<string, string> {
  if (!navyMemo) {
    const declared: Record<string, string> = {};
    for (const file of STYLE_FILES) Object.assign(declared, parseRoot(read(file)));
    for (const [name, value] of Object.entries(navyRepoints())) declared[name.slice(2)] = value;
    navyMemo = resolveAll(declared);
  }
  return navyMemo;
}

export function resolveTokenIn(theme: TokenTheme, name: string): string {
  if (theme === 'graphite') return resolveToken(name);
  const key = name.startsWith('--') ? name.slice(2) : name;
  const tokens = navyTokens();
  if (!Object.hasOwn(tokens, key)) throw new Error(`${name} is not a token`);
  return tokens[key];
}
