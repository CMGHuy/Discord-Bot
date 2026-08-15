import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { VersionsStore } from '../../stores/versions.store';

/**
 * Versions — which ui and bot versions have ever shipped together.
 *
 * `VERSION.json` carries two independently-bumped lines and no record of
 * which values of one go with which values of the other. That pairing exists
 * only in the file's git history, and this workspace is where it is readable.
 *
 * **The matrix, not a table.** The question the page answers is "this ui ran
 * against which backends" — a range question. A table of 24 pairs makes the
 * reader reconstruct those ranges by eye; a row per ui version with a bar
 * spanning its bot versions answers it without reading anything. The dots on
 * the bar are the pairs that actually shipped, which is not the same as the
 * span: a ui version can skip an intermediate bot release, and a bar drawn
 * without dots would claim otherwise.
 *
 * **The wording is deliberately weak, and must stay weak.** Both containers
 * build from one image, so a pair here shipped as a unit — that is all it
 * says. It is not a test result and not a support matrix. `basis` comes from
 * the server and is rendered verbatim rather than paraphrased, so this page
 * cannot drift into promising "tested" while the API says "released
 * together". Combinations that never shipped are blank rather than marked
 * incompatible: nobody has run them, which is a different claim from their
 * being known-bad.
 */
@Component({
  selector: 'sb-versions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [VersionsStore],
  template: `
    <header class="head">
      <h1>Versions</h1>
      @if (store.live(); as live) {
        <span class="now" title="Running now, read from VERSION.json">
          <span class="k">ui</span><span class="v">{{ live.ui }}</span>
          <span class="k">bot</span><span class="v">{{ live.bot }}</span>
        </span>
      }
      @if (store.stale()) {
        <!-- The frozen file is behind VERSION.json. Saying so is the whole
             point: a matrix silently missing the newest release looks
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
    } @else if (!store.rows().length) {
      <p class="muted">
        No version history recorded. Run
        <code>python scripts/dev/build_version_matrix.py</code> to generate it.
      </p>
    } @else {
      @if (store.basis(); as basis) {
        <p class="basis">{{ basis }}</p>
      }

      <!-- Horizontal scroll lives on this wrapper, never on the page: the bot
           axis grows with every backend release and would otherwise push the
           whole layout sideways. -->
      <div class="scroller">
        <div
          class="matrix"
          [style.--cols]="store.botAxis().length"
          role="table"
          aria-label="ui versions against the bot versions they shipped with"
        >
          <div class="corner" role="columnheader">ui \\ bot</div>
          @for (bot of store.botAxis(); track bot) {
            <div class="colhead" role="columnheader">{{ bot }}</div>
          }

          @for (row of store.rows(); track row.ui) {
            <div class="rowhead" [class.current]="row.current" role="rowheader">
              {{ row.ui }}
              @if (row.current) {
                <span class="badge">now</span>
              }
            </div>

            <!-- The track is one grid cell spanning every column, so the bar
                 inside it can be positioned by column number. Painting the
                 bar into the cells themselves would need one element per
                 column and lose the rounded ends. -->
            <div class="track" [style.--start]="row.start" [style.--span]="row.span">
              <div
                class="bar"
                [class.current]="row.current"
                [attr.title]="
                  'ui ' + row.ui + ' shipped with bot ' + row.botMin +
                  (row.botMin === row.botMax ? '' : ' – ' + row.botMax) +
                  ' · ' + row.firstSeen + ' to ' + row.lastSeen
                "
              ></div>
              @for (column of row.shipped; track column) {
                <div class="dot" [class.current]="row.current" [style.--col]="column"></div>
              }
            </div>
          }
        </div>
      </div>

      <ul class="legend">
        <li><span class="swatch bar-swatch"></span>bot versions this ui spanned</li>
        <li><span class="swatch dot-swatch"></span>a pair that actually shipped</li>
        <li class="note">
          {{ store.pairCount() }} pairs
          @if (store.generatedAt(); as at) {
            · recorded {{ at }}
          }
        </li>
      </ul>
    }
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }

    .head { display: flex; align-items: baseline; gap: var(--space-14); flex-wrap: wrap; }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }

    .now { display: inline-flex; align-items: baseline; gap: var(--space-6);
           font-family: var(--font-mono); font-size: var(--text-chip); }
    .now .k { color: var(--text-faint); }
    .now .v { color: var(--text); }

    .stale { color: var(--warn); font-size: var(--text-table); }
    .stale code, .muted code { font-family: var(--font-mono); font-size: var(--text-micro); }

    .error { color: var(--neg); margin: 0; }
    .muted { color: var(--text-muted); margin: 0; }
    .basis { margin: 0; color: var(--text-secondary); font-size: var(--text-table);
             max-width: 68ch; }

    .scroller { overflow-x: auto; padding-bottom: var(--space-4); }

    /* One label column, then one column per bot version. The bot columns are
       fixed-width so a long axis scrolls rather than compressing to unreadable
       slivers. */
    .matrix {
      display: grid;
      grid-template-columns: max-content repeat(var(--cols), 3.4rem);
      align-items: center;
      gap: var(--space-4) 0;
      min-width: max-content;
    }

    .corner, .colhead, .rowhead {
      font-family: var(--font-mono);
      font-size: var(--text-micro);
      color: var(--text-muted);
      white-space: nowrap;
    }
    .corner { padding-right: var(--space-10); color: var(--text-faint); }
    .colhead { text-align: center; padding-bottom: var(--space-6); }

    .rowhead {
      padding-right: var(--space-10);
      color: var(--text-secondary);
      display: flex; align-items: center; gap: var(--space-6);
      /* Sticky so the ui version stays readable once the bot axis is scrolled
         past the viewport — without it the rows lose their labels, which is
         when a matrix stops being one. */
      position: sticky; left: 0;
      background: var(--bg);
    }
    .rowhead.current { color: var(--text); font-weight: 600; }
    .badge {
      font-size: var(--text-micro); text-transform: uppercase;
      letter-spacing: .04em; color: var(--accent);
      border: 1px solid var(--accent-soft); border-radius: var(--radius-chip);
      padding: 0 var(--space-4);
    }

    .track {
      grid-column: 2 / -1;
      display: grid;
      grid-template-columns: repeat(var(--cols), 3.4rem);
      align-items: center;
      height: 1.4rem;
    }

    .bar {
      grid-column: var(--start) / span var(--span);
      grid-row: 1;
      height: .5rem;
      border-radius: 999px;
      background: var(--accent-soft);
      /* Inset so a one-column span still reads as a pill rather than filling
         the cell edge to edge and touching its neighbour. */
      margin: 0 .55rem;
    }
    .bar.current { background: var(--accent); }

    .dot {
      grid-column: var(--col);
      grid-row: 1;
      justify-self: center;
      width: .5rem; height: .5rem;
      border-radius: 50%;
      background: var(--accent);
      /* Ringed in the page background so a dot sitting on the bar stays
         legible against it at every zoom level. */
      box-shadow: 0 0 0 2px var(--bg);
    }
    .dot.current { background: var(--text); }

    .legend {
      display: flex; flex-wrap: wrap; gap: var(--space-14);
      margin: 0; padding: 0; list-style: none;
      font-size: var(--text-micro); color: var(--text-muted);
    }
    .legend li { display: flex; align-items: center; gap: var(--space-6); }
    .legend .note { color: var(--text-faint); }
    .swatch { display: inline-block; }
    .bar-swatch { width: 1.6rem; height: .5rem; border-radius: 999px;
                  background: var(--accent-soft); }
    .dot-swatch { width: .5rem; height: .5rem; border-radius: 50%;
                  background: var(--accent); }
  `,
})
export class Versions {
  protected readonly store = inject(VersionsStore);
}
