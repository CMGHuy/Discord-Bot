import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Placeholder. The real detail view is NG51.
 *
 * `symbol` arrives as an input() rather than through ActivatedRoute, via
 * withComponentInputBinding() -- which makes the parameter a normal signal
 * input and keeps the component testable without a router.
 */
@Component({
  selector: 'sb-ticker-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>{{ symbol() }}</h1><p class="todo">NG51</p>`,
  styles: `
    h1 { margin: 0; font-family: var(--font-mono); font-size: var(--text-title); }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class TickerDetail {
  readonly symbol = input.required<string>();
}
