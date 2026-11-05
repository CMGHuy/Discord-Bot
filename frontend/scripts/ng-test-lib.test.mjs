// node --test frontend/scripts/ng-test-lib.test.mjs
import { strict as assert } from 'node:assert';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { ngTestInvocation, parseNgTestArgs } from './ng-test-lib.mjs';

const CLI = join(dirname(fileURLToPath(import.meta.url)), 'ng-test.mjs');
const NG_JS = ['node_modules', '@angular', 'cli', 'bin', 'ng.js'];

test('parseNgTestArgs resolves the frontend dir and starts with no includes', () => {
  assert.deepEqual(parseNgTestArgs(['some/frontend']), { frontend: resolve('some/frontend'), includes: [] });
});

test('parseNgTestArgs keeps --include specs in order', () => {
  const opts = parseNgTestArgs(['fe', '--include', 'src/a.spec.ts', '--include', 'src/b.spec.ts']);
  assert.deepEqual(opts.includes, ['src/a.spec.ts', 'src/b.spec.ts']);
});

test('parseNgTestArgs accepts --include before the frontend dir', () => {
  assert.deepEqual(parseNgTestArgs(['--include', 'src/a.spec.ts', 'fe']),
    { frontend: resolve('fe'), includes: ['src/a.spec.ts'] });
});

test('parseNgTestArgs requires the frontend dir', () => {
  assert.throws(() => parseNgTestArgs([]), /usage: node frontend\/scripts\/ng-test\.mjs <frontend dir>/);
  assert.throws(() => parseNgTestArgs(['--include', 'src/a.spec.ts']), /usage:/);
});

test('parseNgTestArgs rejects --include without a spec', () => {
  assert.throws(() => parseNgTestArgs(['fe', '--include']), /--include needs a spec path/);
});

test('parseNgTestArgs rejects an unknown flag and a second positional', () => {
  assert.throws(() => parseNgTestArgs(['fe', '--watch']), /unknown flag --watch/);
  assert.throws(() => parseNgTestArgs(['fe', 'other']), /unexpected argument other/);
});

test('ngTestInvocation runs ng.js test once, from the frontend dir', () => {
  const fe = resolve('fe');
  assert.deepEqual(ngTestInvocation({ frontend: fe, includes: [] }, '/opt/node'), {
    command: '/opt/node', args: [join(fe, ...NG_JS), 'test', '--watch=false'], cwd: fe,
  });
});

test('ngTestInvocation appends one --include pair per spec', () => {
  const fe = resolve('fe');
  const { args } = ngTestInvocation({ frontend: fe, includes: ['src/a.spec.ts', 'src/b.spec.ts'] }, 'node');
  assert.deepEqual(args.slice(1), ['test', '--watch=false', '--include', 'src/a.spec.ts', '--include', 'src/b.spec.ts']);
});

test('ng-test.mjs runs ng.js in the frontend dir and passes its exit code through', () => {
  const fe = mkdtempSync(join(tmpdir(), 'v199-ng-'));
  try {
    mkdirSync(join(fe, ...NG_JS.slice(0, -1)), { recursive: true });
    writeFileSync(join(fe, ...NG_JS),
      'process.stdout.write(JSON.stringify({ cwd: process.cwd(), argv: process.argv.slice(2) }));\nprocess.exit(7);\n');
    const run = spawnSync(process.execPath, [CLI, fe, '--include', 'src/a.spec.ts'], { encoding: 'utf8' });
    assert.equal(run.status, 7);
    const seen = JSON.parse(run.stdout);
    assert.equal(realpathSync(seen.cwd), realpathSync(fe));
    assert.deepEqual(seen.argv, ['test', '--watch=false', '--include', 'src/a.spec.ts']);
  } finally {
    rmSync(fe, { recursive: true, force: true });
  }
});

test('ng-test.mjs exits 2 naming the missing Angular CLI', () => {
  const fe = mkdtempSync(join(tmpdir(), 'v199-ng-'));
  try {
    const run = spawnSync(process.execPath, [CLI, fe], { encoding: 'utf8' });
    assert.equal(run.status, 2);
    assert.match(run.stderr, /no Angular CLI at .*ng\.js -- run npm ci in /);
  } finally {
    rmSync(fe, { recursive: true, force: true });
  }
});

test('ng-test.mjs exits 2 with the usage line when the frontend dir is missing', () => {
  const run = spawnSync(process.execPath, [CLI], { encoding: 'utf8' });
  assert.equal(run.status, 2);
  assert.match(run.stderr, /usage: node frontend\/scripts\/ng-test\.mjs <frontend dir>/);
});
