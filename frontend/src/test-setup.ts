import { flattenedRootCss, readFixture } from './app/ui/testing/resolve-token';

/**
 * Put the real design tokens into the test document.
 *
 * Anything that paints to a canvas — the charts — cannot use `var(--pos)`; it
 * has to read the resolved value out of `getComputedStyle`. Without this file
 * that read comes back empty under jsdom, which is why `chart-theme.ts` used to
 * carry eight hex fallbacks. Those fallbacks were stale within one task of
 * being written (SR3's audit found them still holding the pre-SR2 palette), and
 * a stale fallback does not throw: it silently paints the previous design.
 *
 * **Flattened literals, not the CSS files (spec v167, Amendment 1).** Since
 * v167 the tokens come in tiers: palette.css holds the raw colours and
 * tokens.css refers to them (`--pos: var(--mint-400)`). jsdom resolves neither
 * a nested `var()` inside a custom property nor `color-mix()`, so injecting the
 * files would hand the charts the string `var(--mint-400)`. Instead this
 * injects one `:root` block of literals built from
 * tests/charts/resolved_tokens.json. The real browser still loads the tiers.
 *
 * **Generated, never copied by hand.** The fixture is written by
 * `python scripts/dev/dump_tokens.py`, and two tests keep it honest: the
 * TypeScript resolver must reproduce it (`ui/resolve-token.spec.ts`) and so
 * must the Python one (`tests/charts/test_chart_theme.py`). A token edit
 * without regenerating fails both, so this document cannot fall behind the
 * stylesheet the way the old fallbacks did.
 *
 * **`readFileSync`, not `import … from '…?raw'`.** `?raw` was tried first and
 * fails silently here in a way worth recording: the Angular compiler claims
 * every `.css` import ahead of Vite's `?raw` handler, the import resolves to an
 * **empty string**, and the injected `<style>` ends up empty — so every token
 * read still returns `''` and the only symptom is a chart with no colours.
 * `ui/tokens.spec.ts` hit the same wall and reads the file the same way.
 *
 * Resolved from `process.cwd()` rather than `import.meta.url`, for the reason
 * that file records: under `@angular/build:unit-test` the module's own URL is
 * an `http:` one, which `readFileSync` rejects. `ng test` always runs with the
 * frontend project root as its working directory.
 *
 * Appended to `<head>` on the shared jsdom document, once per worker. Nothing
 * removes it: every test in the process wants the tokens, and a per-test
 * teardown would only create an ordering rule to get wrong.
 */
const style = document.createElement('style');
style.textContent = flattenedRootCss(readFixture());
document.head.appendChild(style);

/**
 * Motion is Off in every spec unless the spec asks (spec v168, Testing).
 *
 * Off renders final values at once -- a count-up writes its text
 * synchronously, a draw-in never clips, an entrance never runs -- so a spec
 * that reads `.textContent` right after one detectChanges() keeps passing.
 * A motion spec opts in with provideMotion('on') (or 'reduced' / 'pending'),
 * and one that needs the preference-driven service uses provideMotion('live');
 * a provider the spec adds later wins over this default.
 *
 * Deviation from the plan: a global, not a TestBed.configureTestingModule
 * beforeEach. Under `ng test` this file is evaluated as a separate module
 * copy from the specs', so importing provideMotion here yields a different
 * MOTION_FIXED token and the provider silently does nothing (probed: the app
 * module evaluates twice, TestBed once). MotionService's MOTION_FIXED root
 * factory reads this key, so no import is needed. Keep the literal in step
 * with MOTION_TEST_DEFAULT_KEY in ui/motion/motion.service.ts.
 */
(globalThis as Record<string, unknown>)['__sbMotionTestDefault'] = 'off';
