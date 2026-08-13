import { defineConfig } from 'vitest/config';

/* Runner config for `@angular/build:unit-test`, wired in via angular.json's
 * `runnerConfig`. Angular merges this over its own generated config.
 *
 * **`ng test` intermittently dies before running anything**, with
 * "[vitest-pool-runner]: Timeout waiting for worker to respond" after
 * exactly 60 seconds. That number is `START_TIMEOUT` in vitest's pool
 * runner -- a hard-coded constant, not an option, so it cannot be raised
 * from here.
 *
 * Two earlier explanations for it were wrong and are recorded so nobody
 * spends the time again: it is not the `forks` pool (switching to threads
 * "fixed" it, then it came back), and it is not parallel worker startup
 * (maxWorkers 1 "fixed" it, then it came back at five spec files). It is
 * load: worker startup on this box occasionally takes longer than a minute
 * while an Angular build or the Python suite is running. **A re-run
 * succeeds.** Treat a fresh timeout as "try again", not as a broken suite.
 *
 * The settings below are kept because fewer workers means fewer chances to
 * trip the timeout, and these tests are pure DOM and logic with no native
 * modules and no shared state -- parallelism was buying wall-clock and
 * nothing else.
 */
export default defineConfig({
  test: {
    /* Injects `src/styles/tokens.css` into the test document, so the charts'
     * `getComputedStyle` reads resolve to the real palette instead of coming
     * back empty (SR35). Appended to the builder's own setup files —
     * `polyfills.js`, `init-testbed.js`, `vitest-mock-patch.js` — by Vite's
     * config merge, NOT replacing them; a replacement would take the TestBed
     * initialiser with it and every spec would fail at once, which is at least
     * a loud failure if this ever changes. */
    setupFiles: ['./src/test-setup.ts'],
    pool: 'threads',
    // Top-level, not under poolOptions: Vitest 4 removed that block, and a
    // config written the old way is accepted, warned about, and ignored --
    // which looks like a fix while changing nothing.
    maxWorkers: 1,
    minWorkers: 1,
    fileParallelism: false,
  },
});
