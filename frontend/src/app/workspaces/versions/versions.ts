import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import { Release } from '../../api/models';
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { ControlRow } from '../../ui/layout';
import { PaginationComponent } from '../../ui/pagination';
import { SectionHead } from '../../ui/section-head';
import { LaneSegment, VersionsStore } from '../../stores/versions.store';

/**
 * Versions — the release timeline behind every component in `VERSION.json`.
 *
 * `VERSION.json` carries N independently-bumped components and no record of
 * which values of one went with which values of another. That pairing exists
 * only in the file's git history, and this workspace is where it is readable.
 *
 * **A strip over a change stream, not a matrix.** A ui×bot matrix has exactly
 * one other axis to draw a grid against; a third component has nowhere to go.
 * A lane per component, laid out on a shared time axis, has no such ceiling —
 * adding a component costs one more row, never a wider page. The change
 * stream below answers "what shipped when" the matrix never could either: a
 * matrix cell says two versions coexisted, not which commit paired them.
 *
 * **The wording is deliberately weak, and must stay weak.** All containers
 * build from one image, so a release here shipped as a unit — that is all it
 * says. It is not a test result and not a support matrix. `basis` comes from
 * the server and is rendered verbatim rather than paraphrased, so this page
 * cannot drift into promising "tested" while the API says "released
 * together".
 */
@Component({
  selector: 'sb-versions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [VersionsStore],
  imports: [Button, ControlRow, PaginationComponent, SectionHead, Async],
  template: `
    <sb-section-head heading="Versions">
      @if (store.stale()) {
        <!-- The frozen file is behind VERSION.json. Saying so is the whole
             point: a timeline silently missing the newest release looks
             complete, which is the one way this page could mislead. -->
        <span actions class="stale" role="status">
          History not regenerated — run <code>scripts/dev/build_version_matrix.py</code>
        </span>
      }
    </sb-section-head>

    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="no-data-yet"
      emptyTitle="No version history"
      emptyHint="Run python scripts/dev/build_version_matrix.py to generate it."
      [skeletonRows]="8"
      [skeletonCols]="3"
      (retry)="store.load()"
    >
      @if (store.basis(); as basis) {
        <p class="basis">{{ basis }}</p>
      }

      <div class="headline">
        <span class="label">Running now</span>
        <sb-control-row>
          @for (component of store.components(); track component) {
            @if (store.current()[component]; as version) {
              <button sb-button variant="chip" type="button" class="chip" [class.on]="isFiltered(component, version)"
                      (click)="store.toggleFilter(component, version)"
                      [attr.title]="component + ' ' + version + ' — click to filter'">
                {{ component }} <strong>{{ version }}</strong>
              </button>
            }
          }
        </sb-control-row>
      </div>

      <div class="strip" #strip>
        @for (lane of store.lanes(); track lane.component) {
          <div class="lane">
            <span class="lane-name">{{ lane.component }}</span>
            <div class="track">
              @if (lane.absentWidth > 0) {
                <div class="absent" [style.left.%]="(1 - lane.absentWidth) * 100"
                     [style.width.%]="lane.absentWidth * 100"
                     title="This component did not exist yet"></div>
              }
              @for (segment of lane.segments; track segment.start) {
                <button sb-button variant="segment" type="button" class="segment" [class.current]="segment.current"
                        [style.left.%]="segment.start * 100"
                        [style.width.%]="segment.width * 100"
                        [style.background]="segment.current ? null : versionTint(segment.version)"
                        (click)="store.toggleFilter(lane.component, segment.version)"
                        (pointerenter)="hovered.set({ lane: lane.component, segment })"
                        (pointerleave)="hovered.set(null)"></button>
              }
            </div>
          </div>
        }
        <div class="bracket-row">
          <div class="bracket" [style.left.%]="store.bracket().start * 100"
               [style.width.%]="store.bracket().width * 100"
               title="The releases listed below"></div>
        </div>
        @if (hovered(); as h) {
          <div class="overlay-row">
            <div class="spotlight" [style.left.%]="h.segment.start * 100"
                 [style.width.%]="h.segment.width * 100"></div>
          </div>
        }
      </div>

      @if (hovered(); as h) {
        <div class="tooltip">
          <strong>{{ h.lane }} {{ h.segment.version }}</strong>
          @for (pair of pairedEntries(h.segment); track pair[0]) {
            <div>paired with: {{ pair[0] }} {{ pair[1] }}</div>
          }
          <div class="when">{{ h.segment.firstSeen }} → {{ h.segment.current ? 'now' : h.segment.lastSeen }}</div>
        </div>
      }

      <div class="legend">
        <span><i class="sw seg"></i>a version was live</span>
        <span><i class="sw abs"></i>the component did not exist yet</span>
        <span><i class="sw cur"></i>running now</span>
        <span><i class="sw brk"></i>the releases listed below</span>
      </div>

      <div class="ticks">
        <span class="now">{{ store.lastDate() }} &#9650; now</span>
        <span>{{ store.firstDate() }}</span>
      </div>

      @if (store.dense()) {
        <p class="section-help">
          Ordered by time; at this density segment widths are approximate — the dates
          above are the ground truth.
        </p>
      }

      @if (store.filter(); as active) {
        <p class="filtered" role="status">
          Showing releases with {{ active.component }} {{ active.version }}.
          <button sb-button variant="link" type="button" class="link" (click)="store.toggleFilter(active.component, active.version)">
            Show all
          </button>
        </p>
      }
      @if (store.filter() && !store.visible().length) {
        <p class="muted muted-reset">No releases carry that version.</p>
      }

      <ul class="stream">
        @for (release of store.visible(); track release.commit) {
          <li class="entry">
            <span class="when">{{ release.date }}</span>
            <div class="what">
              <sb-control-row>
                @for (component of store.components(); track component) {
                  @if (release.versions[component]; as version) {
                    @if (release.changed.includes(component)) {
                      <button sb-button variant="chip" type="button" class="chip moved"
                              (click)="store.toggleFilter(component, version)">
                        {{ component }} {{ previousOf(release, component) }}<strong>{{ version }}</strong>
                      </button>
                    } @else {
                      <span class="chip quiet">{{ component }} {{ version }}</span>
                    }
                  }
                }
              </sb-control-row>
              <p class="subject">{{ release.subject }}</p>
            </div>
          </li>
        }
      </ul>

      <sb-pagination [pagination]="store.pageSpec()" (pageChange)="store.setPage($event)" />
    </sb-async>
  `,
  styles: `
    /* minmax(0, 1fr): an auto track is floored at its widest child, which is
       how one panel takes the page sideways.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }

    .stale code, .muted code { font-family: var(--font-mono); font-size: var(--text-micro); }

    /* .muted itself is forbidden here (the gate blocks redefining the
       selector at all, not just its colour); this only resets the
       browser's default <p> margin, so it is its own class alongside
       .muted in the markup. */
    .muted-reset { margin: 0; }
    .basis { margin: 0; color: var(--text-secondary); font-size: var(--text-table);
             max-width: 68ch; }

    .headline { display: flex; align-items: baseline; gap: var(--space-10); flex-wrap: wrap; }
    .label { font-size: var(--text-micro); color: var(--text-faint);
              text-transform: uppercase; letter-spacing: .04em; }

    /* Chips WRAP and lanes STACK. This is the property the whole design rests
       on: a new component costs vertical space and never horizontal, so the
       page cannot be widened by adding one -- sb-control-row wraps by
       default (v54), which is why these two rows now use it rather than a
       hand-rolled .chips flex rule. Do not replace with a grid. */
    /* font-family/font-size/colour/padding override the chip variant's
       defaults for this denser, monospaced release-version scale; the
       variant owns background, border and the .on state. */
    .chip {
      font-family: var(--font-mono); font-size: var(--text-micro);
      color: var(--text-muted);
      padding: var(--space-2) var(--space-6);
    }
    .chip strong { color: var(--text); font-weight: 600; }
    .chip.on { color: var(--accent); }
    .chip.quiet { color: var(--text-faint); cursor: default; }

    .strip { display: flex; flex-direction: column; gap: var(--space-6);
              position: relative; overflow: hidden; }
    .lane { display: flex; align-items: center; gap: var(--space-8); }
    .lane-name { width: 4.5rem; flex: none; font-family: var(--font-mono);
                 font-size: var(--text-micro); color: var(--text-muted); }
    .track { position: relative; flex: 1; height: 15px; min-width: 0; }
    /* The 2px surface-colour ring is the separator between two segments that
       happen to land on adjacent shades -- not a border drawn AROUND data,
       which is why it is inset rather than added stroke width. Every segment
       gets one, current included, so the seam is consistent end to end. */
    .segment { position: absolute; top: 0; height: 100%; border: 0; padding: 0;
               border-radius: 2px;
               box-shadow: inset 0 0 0 1px var(--bg); }
    .segment.current { background: var(--accent); }
    .absent { position: absolute; top: 0; height: 100%;
              border: 1px dashed var(--border-strong); border-radius: 2px; }
    .bracket-row { position: relative; height: 12px; margin-left: calc(4.5rem + var(--space-8)); }
    .bracket { position: absolute; top: 0; height: 100%; border: 1px solid var(--text-faint);
               border-radius: 3px; background: var(--surface-raised); }

    /* Track-aligned, same left offset as .bracket-row -- an absolutely
       positioned block with only left/right set (no width) auto-sizes to
       exactly the track's own width, the same trick .bracket-row already
       relies on for its own left/width percentages. */
    .overlay-row { position: absolute; top: 0; bottom: 0;
                    left: calc(4.5rem + var(--space-8)); right: 0;
                    pointer-events: none; }
    /* The 9999px spread dims everything outside this element's own left/width
       in one paint -- clipped to .strip's bounds by its overflow: hidden,
       so it never bleeds into the basis line above or the legend below. */
    .spotlight { position: absolute; top: 0; bottom: 0;
                  box-shadow: 0 0 0 9999px var(--overlay-dim);
                  pointer-events: none; }

    /* Same custom-tooltip convention as line-chart.ts's pointer tooltip:
       position: absolute with no explicit left/top, so it renders at its
       static in-flow position (right after .strip, above .legend) rather
       than tracking the cursor -- deliberately, since it must not be
       clipped by .strip's own overflow: hidden. */
    .tooltip { position: absolute; padding: var(--space-6) var(--space-8);
                background: var(--surface-overlay); border: 1px solid var(--border-strong);
                border-radius: var(--radius); font-size: var(--text-micro); color: var(--text);
                display: flex; flex-direction: column; gap: var(--space-2);
                pointer-events: none; }
    .tooltip .when { color: var(--text-faint); }

    .legend {
      display: flex; flex-wrap: wrap; gap: var(--space-14);
      margin: 0; padding: 0; list-style: none;
      font-size: var(--text-micro); color: var(--text-muted);
      margin-left: calc(4.5rem + var(--space-8));
    }
    .legend span { display: flex; align-items: center; gap: var(--space-6); }
    .sw { display: inline-block; width: .8rem; height: .5rem; border-radius: 2px; }
    .sw.seg { background: var(--accent-soft); }
    .sw.abs { background: none; border: 1px dashed var(--border-strong); }
    .sw.cur { background: var(--accent); }
    .sw.brk { background: var(--surface-raised); border: 1px solid var(--text-faint); }

    .ticks {
      display: flex; justify-content: space-between;
      margin-left: calc(4.5rem + var(--space-8));
      font-family: var(--font-mono); font-size: var(--text-micro); color: var(--text-faint);
    }
    .ticks .now { color: var(--text-muted); }

    /* Overrides the global .section-help's own margin/colour/size --
       this caption is fainter and smaller than the standard explanatory
       paragraph, and sits flush against the strip above it. */
    .section-help { margin: 0; color: var(--text-faint); font-size: var(--text-micro); }

    .filtered { margin: 0; font-size: var(--text-table); color: var(--text-secondary); }
    /* Always underlined, not just on hover -- this sits in a sentence and
       must read as an inline link at rest; the variant only underlines on
       hover. font: inherit is the same reasoning that gave the variant its
       name: this button must look like plain running text. */
    .link { border: 0; font: inherit; text-decoration: underline; }

    .stream { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column;
              gap: var(--space-10); }
    .entry { display: flex; gap: var(--space-14); align-items: baseline; }
    .when { flex: none; width: 6rem; font-family: var(--font-mono); font-size: var(--text-micro);
            color: var(--text-faint); }
    .what { min-width: 0; }
    .subject { margin: var(--space-4) 0 0; color: var(--text-secondary);
               font-size: var(--text-table); }
  `,
})
export class Versions {
  protected readonly store = inject(VersionsStore);
  private readonly strip = viewChild<ElementRef<HTMLElement>>('strip');

  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.releases.length === 0 }),
  );

  protected readonly hovered = signal<{ lane: string; segment: LaneSegment } | null>(null);

  /** `Object.entries` for the template's `@for` -- keeps the tooltip's
   *  paired-version rows from needing a pipe or a second computed just to
   *  iterate a plain object. */
  protected pairedEntries(segment: LaneSegment): [string, string][] {
    return Object.entries(segment.pairedWith);
  }

  protected isFiltered(component: string, version: string): boolean {
    const active = this.store.filter();
    return active?.component === component && active?.version === version;
  }

  /**
   * A distinct shade per version, so a lane with many past segments reads as
   * a sequence rather than one undifferentiated block -- the complaint this
   * exists to fix was that every non-current segment shared one flat colour
   * with no boundary between them.
   *
   * **One hue, not one per version.** `styles/tokens.css` reserves five hues
   * for meaning (pos/neg/warn/accent/info) and calls a sixth "a review
   * defect" -- this is exactly the design system's own ordinal case (a
   * version's place in a time-ordered sequence, not a nominal identity), so
   * it stays on the accent hue (252°) and varies only lightness. Hashed from
   * the version string rather than the segment's position so the same
   * version always reads the same shade if it reappears, and so the shade
   * does not shift under a reader's cursor as the strip re-measures.
   */
  protected versionTint(version: string): string {
    let hash = 0;
    for (let i = 0; i < version.length; i++) {
      hash = (hash * 31 + version.charCodeAt(i)) | 0;
    }
    // 38-62%: dark enough to clear the light-band floor against --bg at the
    // low end, and capped 5 points below --accent's own 67% lightness at the
    // high end -- a hash landing near the top must still read as clearly
    // dimmer than "current", never close enough to be mistaken for it.
    const lightness = 38 + (Math.abs(hash) % 25);
    return `hsl(252, 65%, ${lightness}%)`;
  }

  /** "1.2.4 → " for a bump, "· new " for a component's first appearance. The
   *  two are distinguishable because the previous release's value is null,
   *  and they must be: a component appearing is not a component upgrading. */
  protected previousOf(release: Release, component: string): string {
    const all = this.store.releases(); // newest first
    const at = all.indexOf(release);
    const previous = all[at + 1]?.versions[component] ?? null;
    return previous === null ? '· new ' : `${previous} → `;
  }

  /** The floor is a pixel rule, so the store needs the real width.
   *
   *  `typeof ResizeObserver` guards jsdom, which does not implement it: the
   *  store's own `stripWidth: 800` default keeps the page usable there, same
   *  as before the component has measured itself in a real browser. */
  private readonly measure = effect((onCleanup) => {
    const host = this.strip()?.nativeElement;
    if (!host || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) =>
      this.store.setStripWidth(entry.contentRect.width));
    observer.observe(host);
    onCleanup(() => observer.disconnect());
  });
}
