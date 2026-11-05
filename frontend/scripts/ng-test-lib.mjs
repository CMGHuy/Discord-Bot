/** Pure helpers for ng-test.mjs: argument parsing and the spawn description. */
import { join, resolve } from 'node:path';

export const USAGE = 'usage: node frontend/scripts/ng-test.mjs <frontend dir> [--include <spec>]...';

export function parseNgTestArgs(argv) {
  const includes = [];
  let dir;
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--include') {
      const spec = argv[i + 1];
      if (spec === undefined || spec.startsWith('--')) throw new Error('--include needs a spec path');
      includes.push(spec);
      i += 1;
    } else if (token.startsWith('--')) {
      throw new Error(`unknown flag ${token}`);
    } else if (dir === undefined) {
      dir = token;
    } else {
      throw new Error(`unexpected argument ${token}`);
    }
  }
  if (dir === undefined) throw new Error(USAGE);
  return { frontend: resolve(dir), includes };
}

export function ngTestInvocation(opts, execPath) {
  const ngJs = join(opts.frontend, 'node_modules', '@angular', 'cli', 'bin', 'ng.js');
  return {
    command: execPath,
    args: [ngJs, 'test', '--watch=false', ...opts.includes.flatMap((spec) => ['--include', spec])],
    cwd: opts.frontend,
  };
}
