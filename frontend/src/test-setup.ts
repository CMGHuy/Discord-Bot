import { readFileSync } from 'node:fs';
import { join } from 'node:path';

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
 * jsdom's cascade does resolve custom properties declared in an injected
 * `<style>`, so injecting the token file removes the need for a fallback
 * entirely — the test document has the same palette the browser does.
 *
 * **The file is read, never copied.** A helper holding the values as literals
 * would just move the stale-fallback problem somewhere less visible; reading
 * `src/styles/tokens.css` means editing a token changes what the tests see in
 * the same edit.
 *
 * **`readFileSync`, not `import … from '…tokens.css?raw'`.** `?raw` was tried
 * first and fails silently here in a way worth recording: the Angular compiler
 * claims every `.css` import ahead of Vite's `?raw` handler, the import
 * resolves to an **empty string**, and the injected `<style>` ends up empty —
 * so every token read still returns `''` and the only symptom is a chart with
 * no colours. `ui/tokens.spec.ts` hit the same wall (it got a processed style
 * object) and reads the file the same way.
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
style.textContent = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');
document.head.appendChild(style);
