import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * A table row that navigates.
 *
 * A real `<a>` with an href, not a `(click)` on the `<tr>`: middle-click,
 * ctrl-click, "open in new tab" and the status-bar preview all come free, and
 * every one of them is lost the moment a row becomes a div with a handler.
 * Five workspaces had hand-rolled `.row-link` (dashboard, risk, trades,
 * watchlist, ticker-detail) -- all navigate, none open a drawer or anything
 * else, so `link` is the only input this needs.
 */
@Component({
  selector: 'sb-row-link',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `<a class="row-link" [routerLink]="link()"><ng-content /></a>`,
  styles: `
    :host { display: contents; }
    .row-link {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      color: inherit;
      text-decoration: none;
    }
    .row-link:hover { background: var(--surface-raised); text-decoration: none; }
    .row-link:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  `,
})
export class RowLink {
  readonly link = input.required<unknown[]>();
}
