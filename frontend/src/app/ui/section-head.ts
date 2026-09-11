import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * The band at the top of a workspace or panel: a heading, and optionally the
 * controls that act on what it names.
 *
 * All seven workspaces hand-rolled this as `.head` with the same four-line
 * flex rule, which is how seven slightly different gaps and two different
 * heading sizes arrived. The level is an input rather than inferred, because
 * a panel inside a workspace needs an h2 under the workspace's h1 and only
 * the caller knows which it is -- an inferred level would silently produce
 * two h1s on one page.
 *
 * `heading` is optional (R1-11): eight workspaces now use this purely for
 * its actions/status band, since the top bar renders the page title and an
 * empty `<h1>` would be a worse accessibility surface than no heading at all.
 */
@Component({
  selector: 'sb-section-head',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="title-group">
      <ng-content select="[back]" />
      @if (heading(); as h) {
        @if (level() === 1) { <h1>{{ h }}</h1> } @else { <h2>{{ h }}</h2> }
      }
      <span class="status"><ng-content select="[status]" /></span>
    </div>
    <div class="actions"><ng-content select="[actions]" /></div>
  `,
  styles: `
    :host {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: var(--space-10);
    }
    /* margin: 0 -- five of the seven call sites this replaces reset it
       explicitly; without it the browser's default heading margin sits
       inside the flex row as unabsorbed space (flex items don't collapse
       margins the way block layout does), unevenly padding the header. */
    .title-group { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--space-4) var(--space-10); min-width: 0; }
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; overflow-wrap: anywhere; }
    h2 { margin: 0; font-size: var(--text-subhead); font-weight: 600; overflow-wrap: anywhere; }
    .status { display: inline-flex; align-items: baseline; gap: var(--space-8); color: var(--text-secondary); font-size: var(--text-chip); }
    .status:empty { display: none; }
    .actions { display: contents; }
  `,
})
export class SectionHead {
  readonly heading = input<string | null>(null);
  readonly level = input<1 | 2>(1);
}
