import { defineConfig } from 'vitest/config';

/* Runner config for `@angular/build:unit-test`, wired in via angular.json's
 * `runnerConfig`. Angular merges this over its own generated config.
 *
 * `pool: 'threads'` is the whole reason this file exists. Vitest's default
 * `forks` pool never starts a worker on this Windows box -- `ng test` sits
 * for 60 seconds and dies with "Timeout waiting for worker to respond",
 * before running a single test. Threads start immediately. The tests
 * themselves are pure DOM/logic work with no native modules and no reason to
 * need process isolation.
 */
export default defineConfig({
  test: {
    pool: 'threads',
  },
});
