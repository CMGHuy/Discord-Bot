#!/usr/bin/env node
/**
 * Run the Angular unit tests from ANY directory -- no `cd frontend` first,
 * which the repo hooks forbid for agents:
 *
 *   node <wt>/frontend/scripts/ng-test.mjs <wt>/frontend [--include <spec>]...
 *
 * Spawns <frontend>/node_modules/@angular/cli/bin/ng.js test --watch=false
 * with cwd=<frontend> and exits with its status (2 for a usage error or a
 * missing Angular CLI). Same spawn as check-compact-interactions.mjs.
 */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { ngTestInvocation, parseNgTestArgs } from './ng-test-lib.mjs';

let opts;
try {
  opts = parseNgTestArgs(process.argv.slice(2));
} catch (err) {
  console.error(err.message);
  process.exit(2);
}
const { command, args, cwd } = ngTestInvocation(opts, process.execPath);
if (!existsSync(args[0])) {
  console.error(`no Angular CLI at ${args[0]} -- run npm ci in ${cwd}`);
  process.exit(2);
}
const result = spawnSync(command, args, { cwd, stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
