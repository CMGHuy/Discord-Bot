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
 */
@Component({
  selector: 'sb-section-head',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (level() === 1) {
      <h1>{{ heading() }}</h1>
    } @else {
      <h2>{{ heading() }}</h2>
    }
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
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    h2 { margin: 0; font-size: var(--text-subhead); font-weight: 600; }
    .actions { display: contents; }
  `,
})
export class SectionHead {
  readonly heading = input.required<string>();
  readonly level = input<1 | 2>(1);
}
