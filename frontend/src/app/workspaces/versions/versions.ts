import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  viewChild,
} from '@angular/core';

import { Release } from '../../api/models';
import { PaginationComponent } from '../../ui/pagination';
import { VersionsStore } from '../../stores/versions.store';

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
  imports: [PaginationComponent],
  template: `
    <header class="head">
      <h1>Versions</h1>
      @if (store.stale()) {
        <!-- The frozen file is behind VERSION.json. Saying so is the whole
             point: a timeline silently missing the newest release looks
             complete, which is the one way this page could mislead. -->
        <span class="stale" role="status">
          History not regenerated — run <code>scripts/dev/build_version_matrix.py</code>
        </span>
      }
    </header>

    @if (store.error(); as error) {
      <p class="error" role="alert">{{ error }}</p>
    }

    @if (store.empty() && store.loading()) {
      <p class="muted">Loading version history…</p>
    } @else if (!store.releases().length) {
      <p class="muted">
        No version history recorded. Run
        <code>python scripts/dev/build_version_matrix.py</code> to generate it.
      </p>
    } @else {
      @if (store.basis(); as basis) {
        <p class="basis">{{ basis }}</p>
      }

      <div class="headline">
        <span class="label">Running now</span>
        <div class="chips">
          @for (component of store.components(); track component) {
            @if (store.current()[component]; as version) {
              <button type="button" class="chip" [class.on]="isFiltered(component, version)"
                      (click)="store.toggleFilter(component, version)"
                      [attr.title]="component + ' ' + version + ' — click to filter'">
                {{ component }} <strong>{{ version }}</strong>
              </button>
            }
          }
        </div>
      </div>

      <div class="strip" #strip>
        @for (lane of store.lanes(); track lane.component) {
          <div class="lane">
            <span class="lane-name">{{ lane.component }}</span>
            <div class="track">
              @if (lane.absentWidth > 0) {
                <div class="absent" [style.width.%]="lane.absentWidth * 100"
                     title="This component did not exist yet"></div>
              }
              @for (segment of lane.segments; track segment.start) {
                <button type="button" class="segment" [class.current]="segment.current"
                        [style.left.%]="segment.start * 100"
                        [style.width.%]="segment.width * 100"
                        (click)="store.toggleFilter(lane.component, segment.version)"
                        [attr.title]="lane.component + ' ' + segment.version
                          + ' · ' + segment.firstSeen + ' → ' + segment.lastSeen"></button>
              }
            </div>
          </div>
        }
        <div class="bracket-row">
          <div class="bracket" [style.left.%]="store.bracket().start * 100"
               [style.width.%]="store.bracket().width * 100"
               title="The releases listed below"></div>
        </div>
      </div>

      <ul class="stream">
        @for (release of store.visible(); track release.commit) {
          <li class="entry">
            <span class="when">{{ release.date }}</span>
            <div class="what">
              <div class="chips">
                @for (component of store.components(); track component) {
                  @if (release.versions[component]; as version) {
                    @if (release.changed.includes(component)) {
                      <button type="button" class="chip moved"
                              (click)="store.toggleFilter(component, version)">
                        {{ component }} {{ previousOf(release, component) }}<strong>{{ version }}</strong>
                      </button>
                    } @else {
                      <span class="chip quiet">{{ component }} {{ version }}</span>
                    }
                  }
                }
              </div>
              <p class="subject">{{ release.subject }}</p>
            </div>
          </li>
        }
      </ul>

      <sb-pagination [pagination]="store.pageSpec()" (pageChange)="store.setPage($event)" />
    }
  `,
  styles: `
    /* minmax(0, 1fr): an auto track is floored at its widest child, which is
       how one panel takes the page sideways.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }

    .head { display: flex; align-items: baseline; gap: var(--space-14); flex-wrap: wrap; }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }

    .stale { color: var(--warn); font-size: var(--text-table); }
    .stale code, .muted code { font-family: var(--font-mono); font-size: var(--text-micro); }

    .error { color: var(--neg); margin: 0; }
    .muted { color: var(--text-muted); margin: 0; }
    .basis { margin: 0; color: var(--text-secondary); font-size: var(--text-table);
             max-width: 68ch; }

    .headline { display: flex; align-items: baseline; gap: var(--space-10); flex-wrap: wrap; }
    .label { font-size: var(--text-micro); color: var(--text-faint);
              text-transform: uppercase; letter-spacing: .04em; }

    /* Chips WRAP and lanes STACK. This is the property the whole design rests
       on: a new component costs vertical space and never horizontal, so the
       page cannot be widened by adding one. Do not replace with a grid. */
    .chips { display: flex; flex-wrap: wrap; gap: var(--space-6); }
    .chip {
      font-family: var(--font-mono); font-size: var(--text-micro);
      color: var(--text-muted); background: var(--surface-raised);
      border: 1px solid var(--border); border-radius: var(--radius-chip);
      padding: var(--space-2) var(--space-6); cursor: pointer;
    }
    .chip strong { color: var(--text); font-weight: 600; }
    .chip.on { border-color: var(--accent); color: var(--accent); }
    .chip.moved { cursor: pointer; }
    .chip.quiet { color: var(--text-faint); cursor: default; }

    .strip { display: flex; flex-direction: column; gap: var(--space-6); }
    .lane { display: flex; align-items: center; gap: var(--space-8); }
    .lane-name { width: 4.5rem; flex: none; font-family: var(--font-mono);
                 font-size: var(--text-micro); color: var(--text-muted); }
    .track { position: relative; flex: 1; height: 15px; min-width: 0; }
    .segment { position: absolute; top: 0; height: 100%; border: 0; padding: 0;
               border-radius: 2px; background: var(--accent-soft); cursor: pointer; }
    .segment.current { background: var(--accent); }
    .absent { position: absolute; left: 0; top: 0; height: 100%;
              border: 1px dashed var(--border-strong); border-radius: 2px; }
    .bracket-row { position: relative; height: 12px; margin-left: calc(4.5rem + var(--space-8)); }
    .bracket { position: absolute; top: 0; height: 100%; border: 1px solid var(--text-faint);
               border-radius: 3px; background: var(--surface-raised); }

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

  protected isFiltered(component: string, version: string): boolean {
    const active = this.store.filter();
    return active?.component === component && active?.version === version;
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

  /** The floor is a pixel rule, so the store needs the real width. */
  private readonly measure = effect((onCleanup) => {
    const host = this.strip()?.nativeElement;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) =>
      this.store.setStripWidth(entry.contentRect.width));
    observer.observe(host);
    onCleanup(() => observer.disconnect());
  });
}
