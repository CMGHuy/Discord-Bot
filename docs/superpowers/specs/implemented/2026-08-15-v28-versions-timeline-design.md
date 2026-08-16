# v28 — Versions: from a two-component matrix to an N-component release timeline

Version: ui 1.3.1 · bot 1.1.2
Bump: `ui minor (1.3.x → 1.4.0)` · `bot none` — the Versions workspace is
replaced rather than adjusted: a different primary visualisation, a different
question answered, and a payload that shares no field names with the old one.
Someone who used the page yesterday has to look at it anew, which is the shape
of a minor in `working-conventions.md`. The precedent is that *adding* this
workspace earned `ui 1.3.0`; replacing what it draws is the same order of
change. The Discord bot is untouched. If it lands feeling smaller than that,
amend this line in the closing commit and say why — see "The header block" in
`document-conventions.md`.

## Goal

Replace the ui×bot matrix in `frontend/src/app/workspaces/versions/versions.ts`
with a visualisation that (a) stays readable at hundreds of versions and (b)
accepts a third, fourth and fifth component without a redesign.

Two questions define "works", both named by the person who uses the page:

1. **What is running together now, and how did we get here?** The current tuple
   is the headline; history is the context for "when did this change".
2. **What did version X ship with?** Pick any component version, see the full
   tuple(s) it shipped alongside.

## Why the matrix fails — measured, not asserted

Both failures are arithmetic, and both were confirmed against the committed
`swingbot/admin/version_history.json` on 2026-08-15.

**It draws a cross-product to represent a log.** 16 ui × 16 bot = 256 cells,
26 of them filled: **10.2% fill**. Cells grow as O(versions²) while the data
grows as O(releases). The six weeks from 2026-07-05 to 2026-08-15 produced 32
version bumps — roughly 5/week. A year of that is ~200 versions and a 100×100
grid at ~2% fill. The complaint that it is "hard to track at 1000" is not
hypothetical; it is four years away at the observed rate, and unreadable long
before that.

**Its central metaphor draws something that mostly does not exist.** The matrix
renders each ui version as a *bar spanning its range of bot versions*. In the
real data `bot` has been `1.1.2` for the last **ten** consecutive ui releases,
and six consecutive ui versions carry a range of `1.1.2..1.1.2` — a span of
one. The bar is a single column almost every time. Worse, the fact it obscures
is the interesting one: the components move at wildly different cadences, and
the matrix has no way to say so.

**It cannot represent a third component at all.** A 2D grid gives each
component an axis. A third component needs a third axis; there isn't one. This
is not a rendering difficulty to be solved with scrolling — it is a
representational impossibility, and it is why the fix is a new data model and
not new CSS.

## Non-goals

- **No compatibility claim.** A pair means "these shipped as a unit", nothing
  more. Not tested-together, not supported-together. The server's `basis`
  string stays the single source of that wording and is still rendered
  verbatim, so the page cannot drift into promising more than it knows.
- **No zoom or pan on the timeline strip.** Decided against in brainstorming:
  the full-history strip plus a page bracket answers both questions without a
  control to build, learn, or keep in sync with the stream.
- **No release diffing** and no "compare two tuples" view. YAGNI.
- **`VERSION.json`'s format does not change.** Adding a component is adding a
  key to it; that is the whole interface.

## 1. Component discovery — the interface for adding a component

Components are **discovered from `VERSION.json`'s own keys**: every key that is
not a `*_updated` stamp.

```python
def _components(doc: dict) -> list[str]:
    return [k for k in doc if not k.endswith("_updated")]
```

Adding `worker` to `VERSION.json` is therefore the entire operation. No
generator edit, no API edit, no SPA edit, no migration.

**Why key-discovery rather than a declared list.** A declared list (a constant
in the generator, or a new `components: [...]` field) is a second place for the
truth to live, and the failure mode is silent: bump a component that is not on
the list and it vanishes from history rather than erroring. `VERSION.json` is
already the authority for what the versions *are*; making it the authority for
what the components are keeps that at one.

**The `*_updated` exclusion is a real constraint, and it is load-bearing.** The
file currently carries `ui_updated` and `bot_updated` timestamps alongside the
versions. A component may therefore never be named `something_updated`. Record
this in the generator as a comment at the filter, because the failure is
invisible: such a component would simply never appear.

**Ordering.** `components` in the payload is the union across all history, in
first-appearance order (oldest release first, then key order within a release).
Not sorted alphabetically: lane order should be stable as components are added,
and alphabetical order re-sorts every existing lane the day someone adds
`api`. First-appearance order only ever appends.

## 2. The absent-component rule

A component missing from a historical `VERSION.json` gets `null` in that
release's `versions`, and **never appears in `changed`**.

This distinction — "did not exist yet" versus "unchanged" — is created by the
N-component requirement and does not exist today. It must be drawn, not
implied: a `worker` lane rendered flat back to July claims the component
existed in July.

**It also replaces a guard that would otherwise delete history.** The generator
currently reads:

```python
ui, bot = doc.get("ui"), doc.get("bot")
if not ui or not bot:
    continue          # ← drops the release entirely
```

Add `worker` today and every historical release still has `ui` and `bot`, so
nothing breaks *yet*. But the same guard generalised carelessly — "skip any
release missing a component" — would drop **every release before the component
was added**, i.e. all of history, the first time anyone extends the file. The
correct generalisation is: keep a release if it has **at least one** known
component; record the missing ones as `null`.

## 3. The payload

`ui_versions`, `bot_versions`, `pairs` and `ranges` are removed. All four are
cross-product artefacts of the matrix.

**Verified on 2026-08-15**: `git grep` over `*.py` and `*.ts` finds readers only
in the files this work already rewrites — `build_version_matrix.py`,
`api_v1/versions.py`, `models.ts`, `versions.store.ts`, `versions.ts` and their
four test files. The only other hits are false positives on the substring
(`arranges` in `data-table.types.ts`, "ranges" in a comment in
`test_exit_sim_scaleout.py`). Nothing outside the plan's own file set depends
on these fields, so this is a clean break rather than a deprecation.

```json
{
  "generated_at": "2026-08-15 12:01:51 UTC",
  "basis": "Versions observed together in VERSION.json. …",
  "components": ["ui", "bot"],
  "current": { "ui": "1.3.1", "bot": "1.1.2" },
  "releases": [
    {
      "date": "2026-08-15",
      "commit": "123d2443",
      "subject": "release(ui): 1.3.1 -- the shell chrome does what it says",
      "versions": { "ui": "1.3.1", "bot": "1.1.2" },
      "changed": ["ui"]
    }
  ]
}
```

`releases` is **oldest first** on the wire, matching how the generator walks
git; the SPA reverses for display. One direction on the wire and one reversal
in one place beats two conventions that can disagree.

### `changed` is derived by the generator, never by the SPA

`changed` lists the components whose value differs from the *previous* release.

**Why server-side.** It is a property of the sequence, not of a release. A SPA
computing it would recompute on every render, would need the full ordered list
in hand to render any single row (breaking pagination), and would have to
special-case the first release — where every component is new — in a second
place. The generator already holds the whole ordered walk.

**First release.** `changed` is every component present. That is correct rather
than a special case to suppress: at the first recorded release, every component
did just appear.

**A component's first appearance mid-history** is in `changed` too, and is
distinguishable from an ordinary bump because the previous release's value for
it is `null`. The SPA renders that as "· new" rather than "old → new"; the rule
lives in the store, once.

## 4. The API

`GET /api/v1/versions` keeps its shape at the top level: the frozen document,
plus `live` and `stale`.

`stale` generalises from two hardcoded comparisons to a dict comparison of the
live `VERSION.json` components against the frozen `current`. Its meaning is
unchanged: someone bumped a version without re-running the generator.

**`stale` must also go true when the component *sets* differ**, not only when a
shared component's value differs. Someone adding `worker` to `VERSION.json`
without regenerating is exactly the case where the page would otherwise render
a confidently complete history that is missing a whole lane.

`_load_history()`'s empty-shape fallback updates to the new field names. Its
behaviour is deliberately unchanged: a checkout where the generator has never
run renders "no history recorded", not an error toast.

## 5. The SPA

### `VersionsStore`

Geometry stays in the store, for the reason the current store already gives:
deriving it in the template means multiple passes per row inside change
detection, and multiple places for an off-by-one to disagree.

- `components()` — lane and chip order, straight from the payload.
- `releases()` — newest first (the one reversal).
- `current()` / `live()` / `stale()` / `basis()` / `generatedAt()` — as today.
- `page()`, `pageSize()`, `filter()` — pagination and the version filter.
- `visible()` — the releases on the current page after filtering.
- `lanes()` — per component, the segments to draw. See geometry below.
- `bracket()` — `{ startFraction, widthFraction }` for the visible page.

### The strip's x-axis is **time**, and this is the subtle part

Release index would space every release equally. That destroys the signal the
strip exists to carry: "bot sat still for eight days while ui bumped ten times"
is only visible when the x-axis is time.

**The trap: day-resolution dates with same-day releases.** `_states()` reads
`git log --date=short`, so every timestamp is a date with no time. The real
data already has **four releases on 2026-08-14 and three on 2026-08-15**. On a
six-week axis one day is ~2.4% of the width, so four same-day releases are
~0.6% each — sub-pixel at any realistic strip width. Rendered naively they
disappear, and the strip silently under-reports exactly the burst activity it
is meant to show.

**The rule.** Every segment gets a **minimum width floor** (2px, expressed as a
fraction of the measured strip width). Segments are laid out by date; any
segment below the floor is raised to it, and the surplus is taken proportionally
from segments above the floor so the lane still sums to 100%.

Consequences to accept and to write down, because each looks like a bug:

- Same-day releases render as adjacent minimum-width slivers. That reads
  correctly as "several releases that day" and is the intended outcome.
- With enough floored segments the lane's time axis is locally compressed — the
  strip is honest about *order* and approximate about *duration* once density
  is high. The date ticks below it are the ground truth.
- A lane where every segment is floored has degraded to a uniform stripe. This
  is the 1000-version case and is the accepted trade: at that density the strip
  is a cadence texture, and the stream below is the lookup surface.

**Absent leading period.** A component's lane before its first appearance is not
a segment: it is a hatched region carrying the label "did not exist yet". It
takes its width from the same time axis, so lanes stay vertically aligned.

### The component

Four stacked regions, top to bottom:

1. **Headline** — the live tuple as one chip per component. Wraps.
2. **Strip** — one lane per component, full history, with the page bracket.
3. **Stream** — one entry per release, newest first. Changed components render
   as prominent `old → new` chips; unchanged ones as dimmed `name value`;
   absent ones are omitted entirely.
4. **Pagination** — the existing `sb-pagination`.

**Nothing widens with component count.** Chips wrap, lanes stack. Each new
component costs vertical space and never horizontal — this is the property that
answers the original objection, and it is worth a test rather than a comment.

### Lookup, without new UI

Clicking any chip — headline, strip segment or stream — sets `filter()` to that
`{component, version}` pair. The stream narrows to releases containing it; the
bracket narrows to the matching span. Clicking again clears.

This answers question 2 with a filter rather than a second view, which is why
there is no separate drill-down panel in the layout.

## 6. Annotation and explanatory copy

Every non-obvious mark on this page carries an explanation in the page itself,
not only in the code. The current page's `basis` paragraph is the precedent;
this extends it, because a timeline has more marks that can be misread than a
table does.

- **A legend**, always visible, naming each mark: a solid segment (a version was
  live), a hatched region (the component did not exist yet), the bracket (the
  releases listed below), a bright segment (running now).
- **Axis ticks** with dates under the strip, plus an explicit `▲ now` at the
  right edge. Without ticks a compressed lane is unreadable as time at all.
- **`title` tooltips** on every segment and chip, giving the full
  `component version · first_seen → last_seen` that the compressed geometry
  cannot show inline.
- **The `basis` string, verbatim**, exactly as today — it is the page's
  disclaimer that a pair is a release fact and not a test result.
- **A one-line note on the floor** where the strip is dense: the strip is
  ordered by time and approximate in width at high density. A reader comparing
  a sliver to a date tick deserves to know why they disagree.
- **Named empty and absent states**: "no history recorded" (generator never
  run) is distinct from "this component has no releases in the filtered range".

Code comments follow the house style already in these files — say *why*, and
say what breaks if the line is changed. The three that must be written because
the failure is silent: the `*_updated` exclusion, the at-least-one-component
guard, and the width floor's redistribution.

## 7. States

- **Loading, first time** — "Loading version history…".
- **Empty** — generator never run: the existing copy, unchanged.
- **Error** — the existing `unavailable` handling, unchanged.
- **Stale** — the existing warning, extended to fire on a component-set
  difference as well as a value difference.
- **Single release** — the strip is one full-width segment per component. It
  must not divide by zero computing fractions.
- **One component** — lanes and chips render as a list of one. No special case.

## 8. Testing

**Generator** (`tests/scripts/test_build_version_matrix.py`, extended):
component discovery from keys; `*_updated` exclusion; a release missing a
component yields `null` and is kept, not skipped; `changed` derivation
including the first release and a mid-history first appearance; dedup of a
repeated tuple still extends `last_seen`; the existing semver-sort tests are
kept as-is; the committed-file-matches-generator test is kept and updated to
the new field names.

**Store** (`versions.store.spec.ts`, rewritten): newest-first ordering; lane
geometry sums to 1 within tolerance; the width floor raises a sub-floor segment
and takes the surplus from the others; the hatched leading region is produced
for a late-appearing component; bracket maths for first, middle and last page;
filter narrows both stream and bracket.

**API** (`tests/admin/test_api_v1_versions.py`): the new payload shape; `stale`
on a value difference; `stale` on a component-set difference.

**Component**: a test asserting no horizontal overflow as components are added
— the property in §5 that the whole design rests on.

## 9. Migration

The frozen `swingbot/admin/version_history.json` is regenerated as part of the
work. There is no dual-format period and no reader for the old shape: the file
is generated, committed, and consumed by exactly one endpoint and one workspace,
all of which change in the same plan.

**Regeneration ordering carries the trap `working-conventions.md` now
documents**: the generator walks `git log` for `VERSION.json`, so it must run
*after* the release commit or the newest release records as
`"commit": "uncommitted"`.

## Parallelisation

- **Sequential — the payload is a chain.** The generator defines the shape, the
  API serves it, the store reads it, the component draws it. Each task consumes
  the previous task's output, and there is no point at which two of them touch
  disjoint files with no contract dependency.
- **One genuine parallel pair, at the end:** the component test in §8 and the
  annotation/copy pass in §6 touch `versions.ts` — so they are *not* parallel
  with each other, but either may run alongside the generator-side test
  extension in `tests/scripts/`, which shares no file with the frontend.
- This working tree is shared between sessions. Two agents on `versions.ts`
  overwrite rather than merge.
