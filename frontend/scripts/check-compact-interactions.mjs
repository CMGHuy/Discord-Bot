#!/usr/bin/env node
/** Native compact-row interaction regression; run from any directory.
 * Uses installed Chrome by default; SB_COMPACT_BROWSER_CHANNEL selects an
 * alternative Playwright channel. No server, credentials or database needed.
 * Normal Angular unit runs keep the compiled-DOM checks and skip the browser.
 */
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = dirname(dirname(fileURLToPath(import.meta.url)));
const result = spawnSync(process.execPath, [
  join(frontend, 'node_modules/@angular/cli/bin/ng.js'),
  'test', '--watch=false', '--include', 'src/app/ui/data-table/data-table.spec.ts',
], {
  cwd: frontend,
  stdio: 'inherit',
  env: { ...process.env, SB_COMPACT_BROWSER_TESTS: '1' },
});
if (result.error) throw result.error;
process.exit(result.status ?? 1);
