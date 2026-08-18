Version: ui 1.7.2 · bot 1.2.1
Bump: ui minor (1.7.2 → 1.8.0); bot none

# Versions strip: newest-first axis + paired-version hover

## Problem

The Versions workspace (`frontend/src/app/workspaces/versions/`) draws one
lane per component on a shared time axis, oldest at the left edge and the
current, live segment buried at the far right of a strip that can span
months. The change-stream list below it already reads newest-first (the
store's one deliberate reversal of the wire order); the strip doesn't match
that convention, so the thing a reader most wants — what's running now — is
the least visible part of the page.

Separately, the lanes are laid out on the same time axis specifically so a
reader can tell what shipped together, but nothing on the page surfaces that
pairing directly. To find out "which bot version went out with ui 1.7.0" today
means reading two lanes' worth of segment tooltips and eyeballing which x-ranges
overlap.

## Non-goals

- **Not a compatibility/support matrix.** The page's existing doc comment is
  deliberate: `basis` is rendered verbatim from the server precisely so this
  page cannot drift into claiming two components were *tested* together —
  only that they *shipped* together. This spec's hover feature surfaces real
  pairing data (which versions rode in the same release) and must stay in
  that same register. Wording is "paired with" / "shipped alongside", never
  "compatible".
- Not touching pagination, filtering, the "Running now" chip row, or the
  change-stream list — all three already behave correctly.
- Not adding a settings toggle for axis direction. One convention,
  newest-first, applied everywhere on the page.

## Design

### 1. Strip axis flip

`VersionsStore`'s `lanes()` and `bracket()` computeds place segments on a
`[0, 1]` time fraction, `0` = the earliest release's date, `1` = now. Both
computeds invert every fraction they currently produce:

```
inverted = 1 - start - width
```

applied as the very last step, after `applyFloor` and the run-collapsing
logic — those stay in chronological order internally since the floor
algorithm's iteration order doesn't matter to its result. Only the emitted
`start` (and `bracket().start`) flips.

Everything downstream that reads a fraction (the template's
`[style.left.%]` / `[style.width.%]` bindings) needs no change — it's
consuming an already-inverted number.

`firstDate` / `lastDate` template order swaps: "now ▲" renders first (left),
the earliest date renders last (right) — the `.ticks` row's two spans just
swap position, the underlying computeds are unchanged.

The `absentWidth` region (drawn from the lane's own `start = 0`) inverts the
same way: it now sits at the *right* edge (the component didn't exist yet, so
that's the oldest end of the flipped axis) rather than the left.

### 2. `LaneSegment.pairedWith`

Every `Release.versions` on the wire is already a full snapshot of *every*
component, not just the ones `changed` that release. The lane-building loop
in `lanes()` already resolves, for each run, the specific release row that
closes it out:

```ts
lastSeen: ordered.find((r) => t(r.last_seen) === run.to)?.last_seen ?? '',
```

`pairedWith` reuses that same lookup instead of re-deriving anything:

```ts
export interface LaneSegment {
  // ...existing fields unchanged...
  /** Every other component's version as of this segment's last_seen — the
   *  ceiling reached while this version was active. Never includes the
   *  segment's own component, and never a component that hadn't shipped
   *  yet (null on the wire — absent must not read as a value, same rule
   *  `absentWidth` already enforces for this lane's own component). */
  pairedWith: Record<string, string>;
}
```

Built as:
```ts
const closingRelease = ordered.find((r) => t(r.last_seen) === run.to);
const pairedWith = Object.fromEntries(
  Object.entries(closingRelease?.versions ?? {})
    .filter(([c, v]) => c !== component && v !== null) as [string, string][]
);
```

No new store state, no new API surface — this is a pure derivation from data
the store already has loaded.

### 3. Custom hover tooltip

Segments currently use the native `[attr.title]` tooltip. That can't hold
multiple lines cleanly and can't drive the lane-highlight in part 4, so it's
replaced with a component-local hover signal plus a rendered `.tooltip` div —
the same pattern `line-chart.ts` already uses for its pointer tooltip
(`hoverIndex` signal + `pointermove`/`pointerleave` + absolutely-positioned
div reading `--surface-overlay`/`--border-strong`), not a new convention.

```ts
protected readonly hovered = signal<{ lane: string; segment: LaneSegment } | null>(null);
```

Set on the segment button's `(pointerenter)`, cleared on `(pointerleave)`.
Content:

```
{{ hovered().lane }} {{ hovered().segment.version }}
@for (pair of pairedWith entries) {
  paired with: {{ pair.component }} {{ pair.version }}
}
{{ segment.firstSeen }} → {{ segment.current ? 'now' : segment.lastSeen }}
```

`pairedWith` is already ceiling-only by construction (part 2), so there's no
range-vs-single-value branching in the template — every entry renders the
same way.

### 4. Cross-lane spotlight on hover

`.strip` gains `position: relative` and, when `hovered()` is set, an overlay
element sized to the hovered segment's *flipped* `[start, start+width]`
fraction, spanning the full height of the strip (all lanes at once):

```css
.spotlight {
  position: absolute; top: 0; bottom: 0;
  box-shadow: 0 0 0 9999px var(--overlay-dim);
  pointer-events: none;
}
```

`left`/`width` bound to the hovered segment's fraction, in percent, same as
every other geometry binding on this page. The box-shadow spotlight trick
dims everything *outside* the element's bounds in one paint, across every
lane simultaneously, without touching any other segment's markup or having
to slice a partially-overlapping segment in half. `styles/tokens.css` has no
scrim/dim token today (checked — it's dark-only, no `prefers-color-scheme`
split to worry about) so this adds one: `--overlay-dim: rgba(10, 11, 16,
.72)`, derived from `--bg` (`#0a0b10`) at 72% opacity, alongside the other
`--surface-*` tokens.

Clearing hover removes the element; no transition needed for v1.

## Data flow

No API or backend change. `build_version_matrix.py` / `version_history.json`
are untouched — this is entirely a client-side re-derivation of data already
on the wire (`Release.versions`, already a full per-release snapshot) plus a
coordinate transform on numbers the store already computes.

## Testing

- `versions.store.spec.ts`: none of the existing geometry assertions hard-code
  a direction (they compare relative widths or check `sum === 1`, not literal
  `start` values), so they keep passing unchanged — `applyFloor` itself is
  untouched, the flip is a step applied after it. Add new assertions instead:
  the current (newest) segment of every lane has `start === 0` post-flip
  (algebraically, a run ending at the pre-flip fraction `1` inverts to `0`);
  the earliest release's segment sits at the trailing edge
  (`start + width` closest to `1`). Add a `pairedWith` case using the
  existing `RESPONSE` fixture (worker joins in release `a3`, so `a3`'s ui
  segment's `pairedWith` should read `{ bot: '1.1.2', worker: '0.1.0' }`).
- `versions.spec.ts` (component): hover a segment, assert the tooltip renders
  the paired versions and the "paired with" wording (not "compatible");
  assert the spotlight element's `left`/`width` match the hovered segment's
  flipped fraction.
- No backend tests change.

## Parallelisation

Two files, one PR-sized change — not worth splitting across sessions:

- `versions.store.ts` (axis flip + `pairedWith`) must land before
  `versions.ts` (template/hover/spotlight) can be written against the new
  shape — sequential, not parallel, and both are small enough that
  splitting them across two sessions would cost more in handoff than it
  saves.
