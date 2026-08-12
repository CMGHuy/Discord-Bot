import { defineConfig } from 'vitest/config';

/* Runner config for `@angular/build:unit-test`, wired in via angular.json's
 * `runnerConfig`. Angular merges this over its own generated config.
 *
 * **Everything here is about getting a worker to start at all on this box.**
 * Out of the box, `ng test` sat for 60 seconds and died with "Timeout
 * waiting for worker to respond" without running a test. Switching off the
 * default `forks` pool fixed it for two spec files and then failed again at
 * three -- so the pool type was never the cause; spawning several workers at
 * once is. One worker, one file at a time, starts reliably.
 *
 * The cost is real but small: these are DOM and logic tests with no native
 * modules and no shared state, so parallelism was buying wall-clock and
 * nothing else. If the suite grows enough for that to hurt, raise
 * maxWorkers before reaching for fileParallelism -- staggered starts are
 * what this box seems unable to do, not concurrency itself.
 */
export default defineConfig({
  test: {
    pool: 'threads',
    // Top-level, not under poolOptions: Vitest 4 removed that block, and a
    // config written the old way is accepted, warned about, and ignored --
    // which looks like a fix while changing nothing.
    maxWorkers: 1,
    minWorkers: 1,
    fileParallelism: false,
  },
});
