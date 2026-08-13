# Hex-literal audit — `frontend/src`

**Task:** SR3 of `2026-08-13-v21-spa-refresh.md`
**Date:** 2026-08-13
**Rule audited:** *no hex literals in `frontend/src` outside `styles/tokens.css`*
(plan v21, Global Constraints).

## Method

```bash
cd frontend && grep -rnaE "#[0-9a-fA-F]{3,8}\b" src | grep -v "src/styles/tokens.css"
```

`-a` matters: `analytics.ts` is classified as binary by ripgrep and plain
`grep`, so a search without it silently skips the largest workspace file in the
project. That is how a literal would survive this audit unnoticed.

## Result

Nine hits. One fixed, eight exempt, none unclassified.

### Fixed

| File | Was | Now |
|---|---|---|
| `src/app/ui/button.ts:49` | `color: #001428` on `:host(.primary)` | `color: var(--bg)` |

The literal was dark navy chosen against the old blue accent. It survived the
palette change intact and would have sat on violet, which is exactly the drift
the rule exists to stop. `--bg` on `--accent` clears 4.4:1, and both sides now
move together if the accent changes again.

### Exempt — class 1: documented fallback for a token read

`src/app/ui/chart-theme.ts:39–46`, eight values.

`lightweight-charts` paints to a canvas and cannot resolve `var(--surface)`, so
the theme reads the computed custom properties at chart-creation time. The
literals are the second argument to that read, used only where computed custom
properties come back empty — jsdom, i.e. tests.

**These were stale when the audit ran.** They still held the v20 palette after
SR2 replaced it. That is the failure mode worth recording: a stale fallback
does not throw and does not look broken, it silently paints the previous design
wherever the token read fails. Updated to match `tokens.css`, with a comment
above them stating the condition of the exemption — *these must equal the
tokens they stand in for, and change in the same commit as the tokens do.*

A future audit should re-check the eight values against `tokens.css`, not merely
confirm the exemption is still recorded.

### Exempt — class 2: painted before any stylesheet exists

`src/index.html:15` — `<style>html, body { background: #000000; }</style>`

This paints the page ground before the bundle parses, so that a slow load is a
dark screen rather than a white flash on a UI that is dark by definition. It
cannot reference a token, because the token file has not loaded yet; that is
the entire point of the line.

**Value is wrong as of this audit** — it is the old pure black, not the new
`--bg`. SR6 owns `index.html` and updates it to `#0a0b10`; flagged here so the
two tasks do not each assume the other did it.

## Standing check

The grep above returns exactly the nine lines classified here. Any tenth line
is a defect. Re-run it at each phase gate.
